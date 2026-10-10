from pathlib import Path

from chess_analytics.common import digest, read_json

SQL = Path(__file__).with_suffix(".sql").read_text()


def draw_rate(connection, project):
    numerator, denominator, unknown_results, marked_bots = connection.execute(SQL).fetchone()
    result = {
        "numerator": numerator,
        "denominator": denominator,
        "unknown_results": unknown_results,
        "marked_bots": marked_bots,
        "value": numerator / denominator if denominator else None,
    }
    path = project / "contracts/game_draw_rate.json"
    contract = read_json(path)
    return {
        "metric_id": contract["id"],
        "metric_version": contract["version"],
        "contract_sha256": digest(path),
        "grain": contract["grain"],
        "caveats": contract["caveats"],
        **result,
    }
