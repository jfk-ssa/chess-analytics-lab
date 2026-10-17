"""Compare checked engine tools with the independent engine_v1 reference.

Opening tallies and source annotations always run. Engine searches run only when
`config/engine.json` names the same binary SHA-256 the reference recorded.
A missing engine or a different binary is a skip, not a tool failure.
Node-count differences are reported and do not fail the check. Score, mate,
depth, selective depth, best move, and principal variation must match exactly.
"""

import argparse
import importlib.util
import json
import tempfile
from pathlib import Path

import chess

from chess_analytics.analyst.engine import compare_candidate_moves, evaluate_position
from chess_analytics.analyst.engine_eval import _bound_evidence, score_case_engine
from chess_analytics.analyst.openings import position_continuations
from chess_analytics.common import digest, write_json

PROJECT = Path(__file__).resolve().parents[1]
EXACT_SEARCH = ("white_cp", "white_mate", "depth", "seldepth", "best_move", "pv")
DATASET = "0" * 24


def _reference_module():
    path = Path(__file__).resolve().parent / "reference_engine_v1.py"
    spec = importlib.util.spec_from_file_location("reference_engine_v1", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def check(project: Path) -> dict:
    reference_path = project / "evals/references/engine_v1.json"
    manifest_path = project / "evals/cases/engine_v1_manifest.json"
    if not reference_path.is_file() or not manifest_path.is_file():
        return {"status": "failed", "reason": "engine_v1 reference is not frozen"}
    reference = json.loads(reference_path.read_text())
    manifest = json.loads(manifest_path.read_text())
    cases = json.loads((project / "evals/cases/engine_v1.json").read_text())
    if digest(reference_path) != manifest["reference_sha256"]:
        return {"status": "failed", "reason": "reference hash changed"}
    if reference["case_set_sha256"] != manifest["case_set_sha256"]:
        return {"status": "failed", "reason": "reference is not bound to the case set"}
    module = _reference_module()
    sources = _check_sources(project, module, reference)
    opening = _check_openings(project, module, reference, cases)
    engine = _check_engine(project, module, reference, cases)
    passed = sources["passed"] and opening["passed"] and engine["status"] != "failed"
    return {
        "status": "passed" if passed else "failed",
        "kind": "engine_v1 tool-to-reference check; not model accuracy",
        "sources": sources,
        "opening": opening,
        "engine": engine,
    }


def search_failures(observed: dict, expected: dict) -> list[str]:
    """Exact gates. Node counts are intentionally absent."""
    return [key for key in EXACT_SEARCH if observed.get(key) != expected.get(key)]


def node_delta(observed: dict, expected: dict) -> int | None:
    left = observed.get("nodes")
    right = expected.get("nodes")
    if isinstance(left, bool) or isinstance(right, bool):
        return None
    if not isinstance(left, int) or not isinstance(right, int):
        return None
    return left - right


def cp_loss(best_cp: int | None, candidate_cp: int | None, *, white: bool) -> int | None:
    if best_cp is None or candidate_cp is None:
        return None
    if white:
        return best_cp - candidate_cp
    return candidate_cp - best_cp


def _check_sources(project: Path, module, reference: dict) -> dict:
    fresh = module.source_annotations(project)
    failures = []
    if fresh != reference["source_annotations"]:
        failures.append("source_annotation_drift")
    for row in fresh:
        if row["role"] == "missing_not_zero" and row["white_cp"] is not None:
            failures.append("missing_source_stored_as_value")
        if row["white_mate"] is not None and row["white_cp"] is not None:
            failures.append("mate_stored_as_centipawns")
        if row["equality_with_engine_required"] is not False:
            failures.append("source_equality_required")
    return {"passed": not failures, "annotations": len(fresh), "failures": failures}


def _check_openings(project: Path, module, reference: dict, cases: list) -> dict:
    failures = []
    with tempfile.TemporaryDirectory() as raw:
        directory = Path(raw) / "visits"
        module.materialize_visits(project, directory)
        board = chess.Board()
        tallies = {
            cohort: module.continuation_tally(directory, cohort, board)
            for cohort in ("elite_reference", "rated_public")
        }
        if tallies != reference["opening"]["cohorts"]:
            failures.append("opening_reference_drift")
        tool_project = _opening_project(directory)
        for case in cases:
            if case["category"] != "position_continuations":
                continue
            tally = tallies[case["expected_tool_args"]["cohort"]]
            if not _subset_tally(case["expected_result"], tally):
                failures.append(f"{case['id']}:case")
            result = position_continuations(
                tool_project,
                DATASET,
                cohort=case["expected_tool_args"]["cohort"],
                fen=case["expected_tool_args"].get("fen"),
                moves=case["expected_tool_args"].get("moves"),
            )
            if not _subset_tally(tally, result):
                failures.append(f"{case['id']}:tool")
    return {"passed": not failures, "failures": failures, "cohorts": sorted(tallies)}


def _check_engine(project: Path, module, reference: dict, cases: list) -> dict:
    identity = module.read_engine_config(project)
    if identity is None:
        return {"status": "skipped", "reason": "engine_not_configured"}
    if "reason" in identity:
        return {"status": "skipped", "reason": identity["reason"]}
    recorded = reference["engine"]["binary_sha256"]
    if identity["binary_sha256"] != recorded:
        return {
            "status": "skipped",
            "reason": "engine_binary_differs",
            "configured_sha256": identity["binary_sha256"],
            "reference_sha256": recorded,
        }
    failures = []
    node_deltas = {}
    with tempfile.TemporaryDirectory() as raw:
        bare = _engine_project(Path(raw) / "bare", identity)
        opened = _engine_project(Path(raw) / "opened", identity)
        directory = Path(raw) / "visits"
        module.materialize_visits(project, directory)
        _write_opening(opened, directory)
        for case in cases:
            if not case["requires_engine_binary"]:
                continue
            home = opened if case["requires_opening_fixture"] else bare
            outcome = _one_engine_case(
                home, case, reference["cases"][case["id"]], reference["engine"]["name"]
            )
            node_deltas[case["id"]] = outcome["node_deltas"]
            if outcome["failures"]:
                failures.append({"id": case["id"], "failures": outcome["failures"]})
    return {
        "status": "failed" if failures else "passed",
        "binary_sha256": recorded,
        "engine_name": reference["engine"]["name"],
        "cases": len(node_deltas),
        "failures": failures,
        "node_deltas": node_deltas,
    }


def _one_engine_case(project: Path, case: dict, record: dict, engine_name: str) -> dict:
    args = case["expected_tool_args"]
    if case["expected_tool"] == "evaluate_position":
        result = evaluate_position(
            project, DATASET, fen=args.get("fen"), moves=args.get("moves"), depth=args.get("depth")
        )
        failures = search_failures(result["root"], record["search"])
        failures.extend(_settings_failures(result, engine_name))
        failures.extend(_scored_failures(case, result, _evaluate_expected(case, record)))
        if record.get("equality_with_engine_required") is not False and case.get(
            "source_annotation_id"
        ):
            failures.append("source_equality_required")
        return {
            "failures": failures,
            "node_deltas": [node_delta(result["root"], record["search"])],
        }
    result = compare_candidate_moves(
        project,
        DATASET,
        candidates=args["candidates"],
        cohort=args["cohort"],
        fen=args.get("fen"),
        moves=args.get("moves"),
        depth=args.get("depth"),
    )
    failures = search_failures(result["root"], record["root"])
    failures.extend(search_failures(result["root"]["after_best"], record["after_best"]))
    failures.extend(_candidate_failures(result, record))
    failures.extend(_settings_failures(result, engine_name))
    failures.extend(_scored_failures(case, result, _compare_expected(case, record)))
    deltas = [node_delta(result["root"], record["root"])]
    deltas.append(node_delta(result["root"]["after_best"], record["after_best"]))
    for item, ref in zip(result["candidates"], record["candidates"], strict=True):
        deltas.append(node_delta(item, ref["search"]))
    return {"failures": failures, "node_deltas": deltas}


def _candidate_failures(result: dict, record: dict) -> list[str]:
    failures = []
    white = result["side_to_move"] == "white"
    best_cp = result["root"]["after_best"]["white_cp"]
    for item, ref in zip(result["candidates"], record["candidates"], strict=True):
        if item["uci"] != ref["uci"]:
            failures.append("candidate_order")
            continue
        for key in ("white_cp", "white_mate", "depth"):
            if item.get(key) != ref["search"].get(key):
                failures.append(key)
        formula = cp_loss(best_cp, item["white_cp"], white=white)
        if item["cp_loss_vs_best"] != formula or item["cp_loss_vs_best"] != ref["cp_loss_vs_best"]:
            failures.append("cp_loss")
        if item["is_engine_best"] != ref["is_engine_best"]:
            failures.append("is_engine_best")
    return failures


def _scored_failures(case: dict, result: dict, expected: dict) -> list[str]:
    answer = _synthetic_answer(case, result)
    scoring = {**case, "expected_result": expected, "dataset_id": DATASET}
    scored = score_case_engine(scoring, answer)
    return [] if scored["passed"] else ["rubric:" + ",".join(scored["failures"])]


def _evaluate_expected(case: dict, record: dict) -> dict:
    expected = json.loads(json.dumps(case["expected_result"]))
    expected["root"] = {key: record["search"][key] for key in EXACT_SEARCH}
    return expected


def _compare_expected(case: dict, record: dict) -> dict:
    expected = json.loads(json.dumps(case["expected_result"]))
    expected["root"] = {key: record["root"][key] for key in EXACT_SEARCH}
    expected["root"]["after_best"] = {key: record["after_best"][key] for key in EXACT_SEARCH}
    for item, ref in zip(expected["candidates"], record["candidates"], strict=True):
        item["white_cp"] = ref["search"]["white_cp"]
        item["white_mate"] = ref["search"]["white_mate"]
        item["depth"] = ref["search"]["depth"]
        item["cp_loss_vs_best"] = ref["cp_loss_vs_best"]
        item["is_engine_best"] = ref["is_engine_best"]
    return expected


def _synthetic_answer(case: dict, result: dict) -> dict:
    """An answer envelope so engine-1.0 can see the tool result."""
    args = case["expected_tool_args"]
    evidence = _bound_evidence(DATASET, case["expected_tool"], args, result)
    caveats = ["observed_prefix_only"]
    if case["expected_tool"] in {"evaluate_position", "compare_candidate_moves"}:
        caveats += ["engine_eval_depth_limited", "engine_not_ground_truth"]
    return {
        "status": "answered",
        "dataset_id": DATASET,
        "result": result,
        "evidence_ids": [evidence],
        "evidence": [
            {
                "tool": case["expected_tool"],
                "args": args,
                "result": result,
                "evidence_id": evidence,
            }
        ],
        "caveats": sorted(set(caveats)),
        "interpretation": "descriptive_observed_prefix",
        "tool_steps": 1,
    }


def _settings_failures(result: dict, engine_name: str) -> list[str]:
    engine = result.get("engine") or {}
    if (
        engine.get("threads") != 1
        or engine.get("hash_mb") != 16
        or engine.get("clear_hash") is not True
        or engine.get("name") != engine_name
    ):
        return ["engine_settings"]
    return []


def _subset_tally(expected: dict, observed: dict) -> bool:
    for key, value in expected.items():
        if key not in observed or observed[key] != value:
            return False
    return True


def _opening_project(directory: Path) -> Path:
    project = directory.parent / "opening-project"
    _write_opening(project, directory)
    return project


def _engine_project(project: Path, identity: dict) -> Path:
    write_json(
        project / "config/engine.json",
        {
            "version": "1",
            "binary_path": str(identity["binary"]),
            "binary_sha256": identity["binary_sha256"],
        },
    )
    return project


def _write_opening(project: Path, directory: Path) -> None:
    write_json(
        project / "config/opening-visits.json",
        {
            "version": "1",
            "kind": "visit_shards",
            "snapshot_dir": str(directory.resolve()),
            "manifest_sha256": digest(directory / "manifest.json"),
        },
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check engine_v1 tools against references")
    parser.add_argument("--project", type=Path, default=PROJECT)
    args = parser.parse_args(argv)
    result = check(args.project)
    summary = {
        "status": result["status"],
        "kind": result.get("kind"),
        "reason": result.get("reason"),
        "sources_passed": result.get("sources", {}).get("passed"),
        "opening_passed": result.get("opening", {}).get("passed"),
        "engine_status": result.get("engine", {}).get("status"),
        "engine_reason": result.get("engine", {}).get("reason"),
        "engine_failures": result.get("engine", {}).get("failures"),
        "node_deltas": result.get("engine", {}).get("node_deltas"),
    }
    print(json.dumps(summary, sort_keys=True))
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
