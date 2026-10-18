"""The lineage diagram is a pure function of the dbt manifest."""

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_SPEC = importlib.util.spec_from_file_location("render_dbt_dag", ROOT / "scripts/render_dbt_dag.py")
assert _SPEC is not None and _SPEC.loader is not None
_MODULE = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_MODULE)
render = _MODULE.render
main = _MODULE.main


def _manifest() -> dict:
    return {
        "sources": {
            "source.chess_analytics.published.fact_game": {
                "resource_type": "source",
                "package_name": "chess_analytics",
                "source_name": "published",
                "name": "fact_game",
                "unique_id": "source.chess_analytics.published.fact_game",
            }
        },
        "nodes": {
            "model.chess_analytics.stg_games": {
                "resource_type": "model",
                "package_name": "chess_analytics",
                "name": "stg_games",
                "path": "staging/stg_games.sql",
                "depends_on": {"nodes": ["source.chess_analytics.published.fact_game"]},
            },
            "model.chess_analytics.games": {
                "resource_type": "model",
                "package_name": "chess_analytics",
                "name": "games",
                "path": "marts/games.sql",
                "depends_on": {"nodes": ["model.chess_analytics.stg_games"]},
            },
            "test.chess_analytics.not_null_games_game_key": {
                "resource_type": "test",
                "package_name": "chess_analytics",
                "name": "not_null_games_game_key",
                "depends_on": {"nodes": ["model.chess_analytics.games"]},
            },
        },
        "semantic_models": {
            "semantic_model.chess_analytics.games": {
                "resource_type": "semantic_model",
                "package_name": "chess_analytics",
                "name": "games",
                "depends_on": {"nodes": ["model.chess_analytics.games"]},
            }
        },
        "metrics": {
            "metric.chess_analytics.game_draw_rate": {
                "resource_type": "metric",
                "package_name": "chess_analytics",
                "name": "game_draw_rate",
                "depends_on": {"nodes": ["semantic_model.chess_analytics.games"]},
            }
        },
        "exposures": {
            "exposure.chess_analytics.governed_metric_analyst": {
                "resource_type": "exposure",
                "package_name": "chess_analytics",
                "name": "governed_metric_analyst",
                "depends_on": {"nodes": ["metric.chess_analytics.game_draw_rate"]},
            }
        },
        "metadata": {"generated_at": "this must not appear"},
    }


def test_lineage_diagram_is_deterministic_and_skips_tests():
    first = render(_manifest())
    second = render(json.loads(json.dumps(_manifest())))
    assert first == second
    assert first.endswith("\n")
    assert "this must not appear" not in first
    assert "not_null_games_game_key" not in first
    assert 'n_source_chess_analytics_published_fact_game["published.fact_game"]' in first
    assert '["games semantic"]' in first
    assert "n_model_chess_analytics_stg_games --> n_model_chess_analytics_games" in first
    assert (
        "n_metric_chess_analytics_game_draw_rate --> "
        "n_exposure_chess_analytics_governed_metric_analyst"
    ) in first
    assert "- Sources: 1" in first
    assert "- Exposures: 1" in first
    assert "```mermaid" in first


def test_render_script_check_matches_a_written_file(tmp_path):
    manifest = tmp_path / "manifest.json"
    output = tmp_path / "DBT_LINEAGE.md"
    manifest.write_text(json.dumps(_manifest()))
    assert main(["--manifest", str(manifest), "--output", str(output)]) == 0
    assert main(["--manifest", str(manifest), "--output", str(output), "--check"]) == 0
    output.write_text(output.read_text() + "\n")
    assert main(["--manifest", str(manifest), "--output", str(output), "--check"]) == 1


def test_committed_lineage_script_imports_no_project_package():
    source = (ROOT / "scripts/render_dbt_dag.py").read_text()
    assert "chess_analytics" not in source.split("def _collect")[0]
    assert "import duckdb" not in source
