from pathlib import Path

from chess_analytics.common import digest, read_json

SQL = Path(__file__).with_suffix(".sql").read_text()


def draw_rate(connection, project):
    values = connection.execute(SQL).fetchone()
    result = dict(
        zip(("numerator", "denominator", "unknown_results", "marked_bots"), values, strict=False)
    )
    result["value"] = result["numerator"] / result["denominator"] if result["denominator"] else None
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
