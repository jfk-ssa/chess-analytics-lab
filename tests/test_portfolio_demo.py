"""End-to-end credential-free portfolio demonstration from committed fixtures."""

import json

import pytest

from analyst_m5.core import replay
from analyst_m5.evaluation import score_case_portfolio
from analyst_m5.provider import live_answer, quote_request
from analytics_m4.analysis import current_snapshot
from chess_analytics.common import read_json
from chess_analytics.portfolio_demo import QUESTIONS, run


def test_complete_demo_repeats_and_replays(project, tmp_path):
    workspace = tmp_path / "portfolio"
    first = run(project, workspace)
    second = run(project, workspace)
    assert first["source_snapshot_id"] == second["source_snapshot_id"]
    assert first["analytical_id"] == second["analytical_id"]
    assert first["source_counts"] == second["source_counts"]
    assert first["live_requests"] == second["live_requests"] == 0
    assert first["analyst"]["scored_opening"]["passed"]
    assert first["analyst"]["opening_evidence_ids"]
    assert first["clock_pressure"]["60_plus"]["evaluation_coverage"] is None
    assert first["clock_pressure"]["30_to_59"]["error_proxy_rate"] == 0.5
    demo_project = workspace / "project"
    assert current_snapshot(demo_project).name == first["analytical_id"]
    assert read_json(demo_project / "reports/portfolio-demo.json")["source_kind"] == (
        "synthetic_test_fixture"
    )
    fixture = demo_project / "evals/replay_plans/portfolio-opening.json"
    answer = replay(demo_project, QUESTIONS["opening"], fixture)
    assert answer["dataset_id"] == first["analytical_id"]
    assert answer["evidence_ids"] == first["analyst"]["opening_evidence_ids"]
    mutated = {**answer, "result": {**answer["result"], "numerator": 3}}
    assert score_case_portfolio(first["analyst"]["opening_reference_case"], mutated)[
        "failures"
    ] == ["result_values"]
    config = read_json(project / "config/personal_provider.example.json")
    config.update(
        enabled=True,
        personal_account_acknowledged=True,
        model="offline-test-model",
        max_run_usd=0.1,
        input_usd_per_million=1.0,
        output_usd_per_million=1.0,
        cache_write_usd_per_million=1.25,
        cached_input_usd_per_million=0.2,
    )
    with pytest.raises(ValueError, match="not finite"):
        quote_request(
            demo_project,
            QUESTIONS["opening"],
            {
                **config,
                "input_usd_per_million": 1e308,
                "cache_write_usd_per_million": 1e308,
            },
        )
    with pytest.raises(ValueError, match="finite remaining"):
        live_answer(
            demo_project, QUESTIONS["opening"], None, config=config, remaining_usd=float("nan")
        )
    bad = json.loads(fixture.read_text())
    bad["plan"]["actions"][0]["tool"] = "execute_sql"
    fixture.write_text(json.dumps(bad))
    with pytest.raises(ValueError, match="unsupported tool"):
        replay(demo_project, QUESTIONS["opening"], fixture)


def test_six_dashboard_views_and_empty_buckets(project, tmp_path, monkeypatch):
    streamlit = pytest.importorskip("streamlit")
    from streamlit.testing.v1 import AppTest

    demo_project = tmp_path / "portfolio" / "project"
    run(project, demo_project.parent)
    monkeypatch.setenv("CHESSLAB_PROJECT", str(demo_project))
    app = AppTest.from_file(str(project / "analytics_m4/dashboard.py"), default_timeout=30).run()
    views = (
        "Overview and coverage",
        "Opening comparisons",
        "Clock pressure",
        "Data quality",
        "AI analyst",
        "Evaluation results",
    )
    for view in views:
        if view != views[0]:
            app.sidebar.radio[0].set_value(view).run()
        assert not app.exception, (view, [item.message for item in app.exception])
        if view == "Clock pressure":
            for bucket in ("under_10", "10_to_29", "30_to_59", "60_plus"):
                app.selectbox[0].set_value(bucket).run()
                assert not app.exception, (bucket, [item.message for item in app.exception])
        if view == "AI analyst":
            app.button[0].click().run()
            assert not app.exception
            assert app.json
    assert streamlit is not None
