"""Offline regressions for Decisions response validation and durable campaign caps."""

import json
import shutil

import pytest

from chess_analytics import decisions_study as study
from chess_analytics.routing_study import LABELS, cases


def setup_study(tmp_path, repo):
    root = tmp_path / "study"
    (root / "evals/cases").mkdir(parents=True)
    for name in (
        "jev_routing_v1.tsv",
        "jev_routing_v1_manifest.json",
        "decisions_routing_v1.json",
        "decisions_routing_v1_manifest.json",
    ):
        shutil.copy2(repo / "evals/cases" / name, root / "evals/cases" / name)
    key = root / "work/.env"
    key.parent.mkdir()
    key.write_text("CHESSLAB_OPENAI_API_KEY=offline-placeholder\n")
    return root, key


def response(route="coverage", tokens=100):
    return {
        "model": study.MODEL,
        "answers": [
            {
                "name": "route",
                "type": "choice",
                "choice": route,
                "confidence": 0.9,
                "probabilities": [
                    {"value": label, "probability": float(label == route)} for label in LABELS
                ],
            }
        ],
        "usage": {"input_tokens": tokens},
    }


def test_contract_rejects_invalid_answers():
    assert study.parse_response(response())["route"] == "coverage"
    for mutate in (
        lambda r: r.update(model="other"),
        lambda r: r["usage"].update(input_tokens=True),
        lambda r: r.update(usage=[]),
        lambda r: r["answers"][0].update(name="other"),
        lambda r: r["answers"][0].update(confidence=float("nan")),
        lambda r: r["answers"][0]["probabilities"].append({"value": "coverage", "probability": 0}),
        lambda r: r["answers"][0]["probabilities"][0].update(probability=0.9),
    ):
        raw = response()
        mutate(raw)
        with pytest.raises(ValueError):
            study.parse_response(raw)
    raw = response()
    raw["answers"] = [{"name": "route", "type": "refusal"}]
    assert study.parse_response(raw)["route"] == "fallback"
    assert study.parse_response(raw)["gross_cost_usd"] > 0


def test_campaign_interrupts_remain_reserved_and_cannot_reset_cap(tmp_path, project):
    root, key = setup_study(tmp_path, project)
    frozen = study.preflight(root)
    campaign = root / "work/campaign"
    cap = frozen["total_reserved_cost_usd"]

    def crash(body, token):
        records = list(campaign.glob("attempt-*/cell-*.json"))
        assert len(records) == 1
        assert json.loads(records[0].read_text())["state"] == "pending"
        raise KeyboardInterrupt

    failed = study.run(
        root, frozen, key, campaign, cap, personal_account_acknowledged=True, transport=crash
    )
    assert not failed["complete"]
    assert (
        failed["cumulative_cost"]["unknown_reserved_usd"] == frozen["cells"][0]["reserved_cost_usd"]
    )
    with pytest.raises(ValueError, match="remaining cumulative cap"):
        study.run(
            root, frozen, key, campaign, cap, personal_account_acknowledged=True, transport=crash
        )
    with pytest.raises(ValueError, match="cannot change"):
        study.run(
            root,
            frozen,
            key,
            campaign,
            cap + 0.1,
            personal_account_acknowledged=True,
            transport=crash,
        )
    # A process killed before settlement leaves a pending record with the same cost.
    path = next(campaign.glob("attempt-*/cell-*.json"))
    record = json.loads(path.read_text())
    record["state"] = "pending"
    path.write_text(json.dumps(record))
    assert study.campaign_cost(campaign) == failed["cumulative_cost"]


def test_cap_drift_and_personal_gate_refuse_before_transport(tmp_path, project):
    root, key = setup_study(tmp_path, project)
    frozen = study.preflight(root)
    campaign = root / "work/campaign"

    def forbidden(*args):
        pytest.fail("transport must not run")

    for cap in (0, -1, True, float("nan"), float("inf"), 0.00001):
        with pytest.raises(ValueError):
            study.run(
                root,
                frozen,
                key,
                campaign,
                cap,
                personal_account_acknowledged=True,
                transport=forbidden,
            )
    with pytest.raises(ValueError, match="acknowledgment"):
        study.run(root, frozen, key, campaign, 0.1, transport=forbidden)
    bad = {**frozen, "model": "changed"}
    with pytest.raises(ValueError, match="drifted"):
        study.run(
            root, bad, key, campaign, 0.1, personal_account_acknowledged=True, transport=forbidden
        )
    fresh = study.preflight(root, "fresh", "test")
    manifest_path = root / study.FRESH_MANIFEST
    manifest = json.loads(manifest_path.read_text())
    manifest["independent_owner_review"] = False
    manifest_path.write_text(json.dumps(manifest))
    fresh = study.preflight(root, "fresh", "test")
    with pytest.raises(ValueError, match="owner review"):
        study.run(
            root, fresh, key, campaign, 0.1, personal_account_acknowledged=True, transport=forbidden
        )
    assert not list(campaign.glob("attempt-*"))


def test_mock_repetitions_and_development_only_threshold(tmp_path, project):
    root, key = setup_study(tmp_path, project)
    frozen = study.preflight(root)
    lookup = {r["question"]: r["label"] for r in cases(root, "dev")[0]}

    def mock(body, token):
        assert token == "offline-placeholder"
        question = json.loads(body)["input"].split("\nQuestion: ", 1)[1]
        return response(lookup[question])

    campaign = root / "work/campaign"
    first = study.run(
        root, frozen, key, campaign, 0.1, personal_account_acknowledged=True, transport=mock
    )
    second = study.run(
        root, frozen, key, campaign, 0.1, personal_account_acknowledged=True, transport=mock
    )
    assert first["transport_kind"] == "injected_mock"
    assert first["complete"] and first["scoring"]["correct"] == 40
    assert second["cumulative_cost"]["accounted_gross_usd"] == pytest.approx(0.0008)
    assert study.calibrate(first)["threshold"] == 0
    with pytest.raises(ValueError, match="development"):
        study.calibrate({**first, "split": "test"})
    # Known usage survives an invalid decision and is never treated as free.
    broken = response()
    broken["answers"] = []
    failed = study.run(
        root,
        frozen,
        key,
        campaign,
        0.1,
        personal_account_acknowledged=True,
        transport=lambda *a: broken,
    )
    assert not failed["complete"]
    assert failed["attempt_accounted_gross_usd"] == pytest.approx(0.00001)
    assert failed["cumulative_cost"]["unknown_reserved_usd"] == 0


def test_cli_nonzero_incomplete_and_quotes_offline(tmp_path, project, capsys, monkeypatch):
    root, key = setup_study(tmp_path, project)
    quote_path = root / "work/preflight.json"
    assert study.main(["prepare", "--project", str(root), "--output", str(quote_path)]) == 0
    monkeypatch.setattr(study, "_transport", lambda *a: {"invalid": True})
    code = study.main(
        [
            "run",
            "--project",
            str(root),
            "--preflight",
            str(quote_path),
            "--env-file",
            str(key),
            "--campaign",
            str(root / "work/campaign"),
            "--cap-usd",
            ".1",
            "--personal-account-acknowledged",
        ]
    )
    assert code == 1
    assert "offline-placeholder" not in capsys.readouterr().out


def test_report_does_not_turn_mock_or_mismatched_replay_into_live_evidence(tmp_path, project):
    from chess_analytics.decisions_report import e2e_replay, render

    root, key = setup_study(tmp_path, project)
    frozen = study.preflight(root)
    mock = study.run(
        root,
        frozen,
        key,
        root / "work/campaign",
        0.1,
        personal_account_acknowledged=True,
        transport=lambda *a: response(),
    )
    document = render([mock])
    assert "mock harness evidence only" in document
    assert "40/40" not in document
    with pytest.raises(ValueError, match="historical end-to-end"):
        e2e_replay(project, mock, study.calibrate(mock))
    cases_path = project / "evals/cases/jev_e2e_v1.json"
    rows = json.loads(cases_path.read_text())
    manifest = json.loads((project / "evals/cases/jev_e2e_v1_manifest.json").read_text())
    classifier = {
        "complete": True,
        "suite": "historical_e2e",
        "transport_kind": "injected_mock",
        "case_sha256": manifest["case_sha256"],
        "predictions": [
            {
                "id": row["id"],
                "route": row["route"],
                "probabilities": {row["route"]: 0.9},
                "gross_cost_usd": 0.0001,
            }
            for row in rows
        ],
    }
    result = e2e_replay(
        project,
        classifier,
        {
            "kind": "development_threshold_policy",
            "metric": "chosen_option_probability",
            "threshold": 0.7,
        },
    )
    assert result["kind"] == "offline_retained_answer_replay_not_live_paired_experiment"
    assert result["new_live_analyst_calls"] == 0
    assert result["combined_live_latency_seconds"] is None
    assert result["analyst_fallbacks"] == 24
    classifier["case_sha256"] = "wrong"
    with pytest.raises(ValueError, match="retained answered"):
        e2e_replay(
            project,
            classifier,
            {
                "kind": "development_threshold_policy",
                "metric": "chosen_option_probability",
                "threshold": 0.7,
            },
        )


def test_replay_scores_false_boundary_without_using_labels_to_route(project):
    from chess_analytics.decisions_report import e2e_replay

    rows = json.loads((project / "evals/cases/jev_e2e_v1.json").read_text())
    manifest = json.loads((project / "evals/cases/jev_e2e_v1_manifest.json").read_text())
    classifier = {
        "complete": True,
        "suite": "historical_e2e",
        "transport_kind": "injected_mock",
        "case_sha256": manifest["case_sha256"],
        "predictions": [
            {"id": row["id"], "route": "fallback", "probabilities": {}, "gross_cost_usd": 0}
            for row in rows
        ],
    }
    # A confidently wrong unsupported route must suppress a supported saved answer
    # and be scored as a failure, rather than consulting the expected label to gate.
    supported = next(row for row in rows if row["expected_status"] == "answered")
    prediction = next(p for p in classifier["predictions"] if p["id"] == supported["id"])
    prediction.update(route="unsupported", probabilities={"unsupported": 0.99})
    policy = {
        "kind": "development_threshold_policy",
        "metric": "chosen_option_probability",
        "threshold": 0.7,
    }
    result = e2e_replay(project, classifier, policy)
    outcome = next(r for r in result["outcomes"] if r["id"] == supported["id"])
    assert outcome["accepted_boundary"] and not outcome["used_retained_analyst"]
    assert outcome["observed_status"] == "unsupported" and not outcome["passed"]
    assert result["analyst_fallbacks"] == 31
