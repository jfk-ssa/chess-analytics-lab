"""Compare classifiers without presenting retained-answer replay as a live workflow."""

import argparse
import html
import json
import statistics
from pathlib import Path

from chess_analytics.decisions_study import load_cases
from chess_analytics.routing_report import _matrix
from chess_analytics.routing_study import _json, _sha, _write


def e2e_replay(repo, classifier, policy):
    if not classifier.get("complete") or classifier["suite"] != "historical_e2e":
        raise ValueError("complete historical end-to-end classifier run required")
    if (
        policy.get("metric") != "chosen_option_probability"
        or policy.get("kind") != "development_threshold_policy"
    ):
        raise ValueError("development probability policy required")
    retained = json.loads((repo / "reports/M8-e2e-paired-rescore.json").read_text())
    cases, manifest = load_cases(repo, "historical_e2e", "test")
    if classifier["case_sha256"] != retained["case_sha256"] or (
        classifier["case_sha256"] != manifest["case_sha256"]
    ):
        raise ValueError("replay must use exactly the retained answered cases")
    baseline = {row["id"]: row for row in retained["outcomes"]["baseline"]}
    by_id = {row["id"]: row for row in cases}
    predictions = classifier["predictions"]
    if {p["id"] for p in predictions} != set(baseline) or set(baseline) != set(by_id):
        raise ValueError("replay case identities differ")
    threshold = policy["threshold"]
    results = []
    for p in predictions:
        accept = (
            threshold is not None
            and p["route"] in {"clarify", "unsupported"}
            and p["probabilities"].get(p["route"], 0) >= threshold
        )
        if accept:
            status = "needs_clarification" if p["route"] == "clarify" else "unsupported"
            passed = status == by_id[p["id"]]["expected_status"]
            fallback_cost = 0
        else:
            status = baseline[p["id"]]["observed_status"]
            passed = baseline[p["id"]]["passed"]
            fallback_cost = baseline[p["id"]]["gross_cost_usd"]["openai"]
        results.append(
            {
                "id": p["id"],
                "accepted_boundary": accept,
                "used_retained_analyst": not accept,
                "observed_status": status,
                "passed": passed,
                "replayed_gross_cost_usd": p["gross_cost_usd"] + fallback_cost,
            }
        )
    correct = sum(r["passed"] for r in results)
    gross = sum(r["replayed_gross_cost_usd"] for r in results)
    return {
        "kind": "offline_retained_answer_replay_not_live_paired_experiment",
        "classifier_transport_kind": classifier["transport_kind"],
        "case_sha256": classifier["case_sha256"],
        "cases": len(results),
        "correct": correct,
        "baseline_correct": sum(r["passed"] for r in baseline.values()),
        "analyst_fallbacks": sum(r["used_retained_analyst"] for r in results),
        "replayed_gross_cost_usd": gross,
        "replayed_gross_per_correct_usd": gross / correct if correct else None,
        "new_live_analyst_calls": 0,
        "combined_live_latency_seconds": None,
        "retained_report_sha256": _sha(_json(retained)),
        "threshold_policy": policy,
        "outcomes": results,
        "limitation": (
            "New Decisions labels plus old Luna answers/costs. No combined execution, "
            "cache, latency, Sol benefit or new-answer quality claim."
        ),
    }


def _coverage_chart(curve):
    points = [p for p in curve if p["accepted"]]
    if not points:
        return "<p>No accepted routes at these thresholds.</p>"
    ymax = max(0.10, max(p["error_rate_among_accepted"] for p in points))
    coords = [
        (45 + 360 * p["coverage"], 175 - 140 * p["error_rate_among_accepted"] / ymax, p)
        for p in sorted(points, key=lambda p: p["coverage"])
    ]
    line = " ".join(f"{x:.1f},{y:.1f}" for x, y, _ in coords)
    dots = "".join(
        f'<circle cx="{x:.1f}" cy="{y:.1f}" r="4" fill="#54d5af"><title>'
        f"Threshold {p['threshold']}: {p['coverage']:.1%} coverage; "
        f"{p['error_rate_among_accepted']:.1%} accepted error; "
        f"{p['fallbacks']} fallbacks</title></circle>"
        for x, y, p in coords
    )
    return (
        '<svg viewBox="0 0 440 225" role="img" '
        'aria-label="Coverage versus accepted routing error at probability thresholds" '
        'style="max-width:600px;width:100%">'
        '<path d="M45 35 V175 H405" fill="none" stroke="#a5b7c2"/>'
        f'<polyline points="{line}" fill="none" stroke="#54d5af"/>{dots}'
        '<g fill="#e8eff2" font-size="12">'
        '<text x="35" y="195">0%</text><text x="378" y="195">100%</text>'
        '<text x="140" y="218">Accepted route coverage</text>'
        f'<text x="45" y="22">Accepted error: 0–{ymax:.0%}</text></g></svg>'
    )


def _summary(checkpoint, comparators):
    if checkpoint.get("kind") != "decisions_classifier_checkpoint":
        raise ValueError("Decisions checkpoint required for results summary")
    fresh = [r for r in checkpoint["runs"] if r["suite"] == "fresh"]
    scores = ", ".join(f"{r['correct']}/{r['cases']}" for r in fresh)
    policy = checkpoint["policy"]
    coverage = fresh[0]["policy_coverage"] if fresh else None
    replay = checkpoint["replay"]
    if replay["kind"] != "offline_retained_answer_replay_not_live_paired_experiment":
        raise ValueError("summary requires explicitly labeled retained-answer replay")
    gate = (
        f"At the development-selected {policy['threshold']:.2f} probability threshold, "
        f"{coverage['accepted']}/{fresh[0]['cases']} fresh routes were accepted, with "
        f"{coverage['errors']} observed errors and {coverage['fallbacks']} fallbacks."
        if coverage and policy["threshold"] is not None
        else "The development policy falls back on every case."
    )
    history = next(
        r for r in checkpoint["runs"] if r["suite"] == "historical" and r["split"] == "test"
    )
    historical_rows = []
    jev_run = 0
    for r in comparators:
        if (
            r.get("split") != "test"
            or r.get("case_sha256") != (checkpoint["policy"]["development_case_sha256"])
        ):
            continue
        scoring = r.get("scoring", r)
        kind = r["kind"]
        name = (
            "Rules baseline"
            if "rules" in kind
            else "Existing Luna analyst"
            if "analyst" in kind
            else "Jev"
        )
        if name == "Jev":
            jev_run += 1
            name = f"Jev — run {jev_run}"
        cost = r.get("accounted_gross_usd", 0)
        historical_rows.append(
            f"<tr><td>{name}</td><td>{scoring['correct']}/{scoring['cases']} "
            f"({scoring['accuracy']:.1%})</td><td>${cost:.8f}</td></tr>"
        )
    historical_rows.append(
        f"<tr><td>Decisions API</td><td>{history['correct']}/{history['cases']} "
        f"({history['correct'] / history['cases']:.1%})</td>"
        f"<td>${history['gross_usd']:.8f}</td></tr>"
    )
    routing_table = (
        "<h3>1. Choosing the right task: same 40 historical questions</h3>"
        "<p>Compare rows within this table. These are correct <em>routes</em>, "
        "not correct final chess answers. Jev has two recorded repetitions; "
        "the runs were collected at different times.</p>"
        "<table><tr><th>Method</th><th>Correct routes</th><th>Gross per run</th></tr>"
        + "".join(historical_rows)
        + "</table>"
        "<p><strong>Reading:</strong> Decisions matches the better Jev run (39/40), "
        "and both outperform this simple rules baseline (35/40). "
        "This does not establish a reliable winner between Jev and Decisions.</p>"
    )
    final_arms = checkpoint["retained_final_answer_comparison"]["arms"]
    final_rows = "".join(
        f"<tr><td>{name}</td><td>{arm['passed']}/{arm['total']}</td>"
        f"<td>${arm['gross_usd']:.8f}</td><td>{arm['analyst_calls']}</td>"
        "<td>Retained live paired run</td></tr>"
        for name, arm in [
            ("Analyst baseline", final_arms["baseline"]),
            ("Jev + analyst", final_arms["gated"]),
        ]
    )
    final_table = (
        "<h3>2. Getting the final answer right: same 32 historical questions</h3>"
        "<p>Here, baseline means the Luna analyst answering directly. A gated "
        "path adds a classifier and uses the analyst when needed.</p>"
        "<table><tr><th>Path</th><th>Correct answers</th><th>Gross total</th>"
        "<th>Analyst answers used</th><th>Evidence</th></tr>"
        + final_rows
        + f"<tr><td>Decisions + saved analyst answers</td>"
        f"<td>{replay['correct']}/{replay['cases']}</td>"
        f"<td>${replay['replayed_gross_cost_usd']:.8f} (simulated)</td>"
        f"<td>{replay['analyst_fallbacks']}</td>"
        "<td>Offline replay; no new analyst answers</td></tr></table>"
        "<p><strong>Reading:</strong> All three paths score 31/32. The analyst "
        "baseline is cheapest. Neither gate has demonstrated a final-answer "
        "quality benefit; the Decisions row is replay evidence, not a new live pairing.</p>"
    )
    return (
        '<section class="summary" aria-labelledby="results-summary">'
        '<h2 id="results-summary">Results at a glance</h2>'
        "<p><strong>Keep Decisions as an optional learning experiment.</strong> "
        "Routing results are promising, but the retained-answer replay shows no "
        "correctness gain and higher simulated cost. There is no evidence yet "
        "to justify integrating it into the analyst.</p>"
        + routing_table
        + final_table
        + "<h3>3. Fresh questions: Decisions versus rules only</h3>"
        "<p>Jev and the existing analyst were not run on this fresh 24-question set; "
        "do not compare its scores with the 40-question table above.</p>"
        "<ul>"
        f"<li><strong>Fresh routing:</strong> {html.escape(scores)} across "
        f"{len(fresh)} repetitions; rules scored {checkpoint['fresh_rules_correct']}/"
        f"{fresh[0]['cases']}. Repetitions reuse the same questions.</li>"
        f"<li><strong>Gate behavior:</strong> {gate}</li>"
        f"<li><strong>Total live spend:</strong> "
        f"${checkpoint['accounted_gross_usd']:.7f} gross for "
        f"{checkpoint['live_requests']} Decisions requests, under the approved "
        f"${checkpoint['approved_cumulative_gross_cap_usd']:.2f} cap.</li>"
        f"<li><strong>Final-answer replay:</strong> {replay['correct']}/{replay['cases']}, "
        f"versus baseline {replay['baseline_correct']}/{replay['cases']}; "
        f"{replay['analyst_fallbacks']} retained-answer fallbacks. "
        f"Simulated gated cost: ${replay['replayed_gross_cost_usd']:.8f}.</li>"
        "</ul><p><strong>Evidence limits:</strong> Only 24 fresh language cases, "
        "with owner-reviewed labels. Jev and analyst comparisons use historical "
        "runs. Final-answer replay uses saved Luna answers, makes no new analyst "
        "calls, and measures no combined live latency.</p>"
        "</section>"
    )


def render(reports, comparators=(), checkpoint=None):
    if not reports:
        raise ValueError("at least one Decisions report required")
    groups = {}
    for r in reports:
        if r.get("kind") != "decisions_routing_attempt":
            raise ValueError("unexpected Decisions report")
        groups.setdefault((r["suite"], r["split"], r["case_sha256"]), []).append(r)

    def esc(x):
        return html.escape(str(x), quote=True)

    summary = ""
    if checkpoint is not None:
        if any(
            r.get("transport_kind") != "openai_decisions_api" or not r.get("complete")
            for r in reports
        ):
            raise ValueError("checkpoint summary requires complete live Decisions reports")
        summary = _summary(checkpoint, comparators)
    sections = []
    for (suite, split, digest), runs in groups.items():
        rows = []
        panels = []
        candidates = []
        if suite in {"historical", "fresh"}:
            candidates = [
                r for r in comparators if r.get("case_sha256") == digest and r.get("split") == split
            ]
        for name, r in [(f"Decisions {i + 1}", r) for i, r in enumerate(runs)] + [
            (r.get("model", "Rules"), r) for r in candidates
        ]:
            if r.get("transport_kind") == "injected_mock":
                panels.append(f"<p>{esc(name)}: mock harness evidence only.</p>")
                continue
            if r.get("complete") is False:
                panels.append(f"<p>{esc(name)}: incomplete; no full-run score.</p>")
                continue
            scoring = r.get("scoring", r)
            if "confusion" not in scoring:
                raise ValueError("missing scored confusion matrix")
            cost = r.get("attempt_accounted_gross_usd", r.get("accounted_gross_usd", 0))
            predictions = r.get("predictions", scoring.get("predictions", []))
            durations = [p["elapsed_seconds"] for p in predictions if "elapsed_seconds" in p]
            median = f"{statistics.median(durations):.3f}" if durations else "unmeasured"
            n = scoring["correct"]
            per = f"${cost / n:.8f}" if n else "—"
            rows.append(
                f"<tr><td>{esc(name)}</td><td>{n}/{scoring['cases']}</td>"
                f"<td>${cost:.8f}</td><td>{per}</td><td>{median}</td></tr>"
            )
            panels.append(f"<h3>{esc(name)}</h3>{_matrix(scoring)}")
            if scoring.get("selective_curve"):
                curve_rows = "".join(
                    f"<tr><td>{p['threshold']}</td><td>{p['accepted']}</td>"
                    f"<td>{p['errors']}</td><td>{p['fallbacks']}</td></tr>"
                    for p in scoring["selective_curve"]
                )
                panels.append(
                    "<p>Chosen-option probability thresholds; descriptive, not a "
                    "test-tuned production policy.</p><table><tr><th>Threshold</th>"
                    "<th>Accepted</th><th>Errors</th><th>Fallbacks</th></tr>"
                    + curve_rows
                    + "</table>"
                    + _coverage_chart(scoring["selective_curve"])
                )
        sections.append(
            f"<section><h2>{esc(suite)} / {esc(split)}</h2>"
            f"<p>Case hash: <code>{esc(digest)}</code></p>"
            "<table><tr><th>Path</th><th>Correct routes</th><th>Gross per pass</th>"
            "<th>Gross/correct route</th><th>Median case seconds</th></tr>"
            + "".join(rows)
            + "</table>"
            + "".join(panels)
            + "</section>"
        )
    return (
        """<!doctype html><html lang="en"><meta charset="utf-8">
<title>Chess routing: Decisions comparison</title>
<style>body{font-family:system-ui;max-width:1200px;margin:auto;padding:2rem;background:#101923;color:#e8eff2}
section{margin:2rem 0;padding:1rem;border:1px solid #38505e}h2,h3{color:#54d5af}
table{border-collapse:collapse;font-size:.85rem}
td,th{padding:.5rem;border:1px solid #38505e}.scroll{overflow:auto}
.hit{background:#245545}p,li{line-height:1.5}code{overflow-wrap:anywhere}
.summary{border:2px solid #54d5af;background:#152b2c}li{margin:.6rem 0}</style>
<h1>Decisions routing learning lab</h1>"""
        + summary
        + """<p>Historical sets are inspected development comparisons.
Fresh cases test new phrasing within the
same eight tasks, not a fresh dataset or general chess ability. Retained Jev and analyst runs were
recorded at a different time; analyst latency includes checked tool execution. No production
promotion follows from this small classifier study.</p>"""
        + "".join(sections)
        + "</html>"
    )


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("html", "replay"))
    parser.add_argument("--project", type=Path, default=Path.cwd())
    parser.add_argument("--report", type=Path, action="append", required=True)
    parser.add_argument("--comparator", type=Path, action="append", default=[])
    parser.add_argument("--policy", type=Path)
    parser.add_argument("--checkpoint", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        reports = [json.loads(p.read_text()) for p in args.report]
        if args.mode == "replay":
            if len(reports) != 1 or not args.policy:
                raise ValueError("replay requires one report and development policy")
            result = e2e_replay(args.project, reports[0], json.loads(args.policy.read_text()))
            _write(args.output, result)
        else:
            comparators = [json.loads(p.read_text()) for p in args.comparator]
            args.output.parent.mkdir(parents=True, exist_ok=True)
            checkpoint = json.loads(args.checkpoint.read_text()) if args.checkpoint else None
            if checkpoint is not None:
                expected = checkpoint["files"]
                if {p.name for p in args.report} != set(expected) or any(
                    _sha(p.read_bytes()) != expected[p.name] for p in args.report
                ):
                    raise ValueError("summary checkpoint does not match supplied report files")
            args.output.write_text(render(reports, comparators, checkpoint))
        print(args.output)
        return 0
    except (OSError, ValueError, KeyError, TypeError) as exc:
        parser.exit(1, f"decisions report: {exc}\n")


if __name__ == "__main__":
    raise SystemExit(main())
