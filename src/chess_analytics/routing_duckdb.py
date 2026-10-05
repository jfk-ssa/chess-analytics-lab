"""Offline DuckDB question-table exercise and explicit Jev SQL preview."""

import argparse
import json
from pathlib import Path

import duckdb

from chess_analytics.routing_study import LABELS, _write, cases, rule_route, score


def sql_preview() -> str:
    """This SQL requires a compatible, separately installed Jev extension."""
    options = "[" + ", ".join("'" + value + "'" for value in LABELS) + "]"
    question = (
        "Select the primary Chess Analytics Lab route. Missing referent: clarify. "
        "Out-of-scope, causal, personal or live request: unsupported. "
        "Otherwise choose the matching opening, clock or coverage route."
    )
    return (
        "-- Run only with an explicit key and gross cap in an isolated DuckDB version.\n"
        "-- INSTALL/LOAD are intentionally omitted: pinned DuckDB 1.4.1 has no Jev binary.\n"
        "SET jev_model = 'jev-1.13.0';\n"
        "SET jev_batch_size = 20;\n"
        "SET jev_concurrency = 1;\n"
        "SET jev_max_retries = 0;\n"
        "SET jev_max_rows_per_statement = 40;\n"
        "SET jev_max_chars_per_statement = 16000;\n"
        "SELECT id, label, jev_eval(struct_pack(question := question), "
        f"'{question}', 'choice', {options}) AS judgment\n"
        "FROM routing_questions ORDER BY id;\n"
        "SELECT jev_stats();\n"
    )


def offline_replay(project: Path, split: str, database: Path) -> dict:
    selected, manifest = cases(project, split)
    database.parent.mkdir(parents=True, exist_ok=True)
    if database.exists():
        raise ValueError("use a fresh isolated DuckDB path")
    connection = duckdb.connect(str(database))
    try:
        connection.execute(
            "CREATE TABLE routing_questions(id VARCHAR PRIMARY KEY, split VARCHAR, "
            "question VARCHAR, label VARCHAR)"
        )
        connection.executemany(
            "INSERT INTO routing_questions VALUES (?, ?, ?, ?)",
            [(row["id"], row["split"], row["question"], row["label"]) for row in selected],
        )
        rows = connection.execute(
            "SELECT id, label, question FROM routing_questions ORDER BY id"
        ).fetchall()
        predictions = [{"id": row[0], "route": rule_route(row[2])} for row in rows]
        scoring = score(selected, predictions, "duckdb_rules_replay")
        report = {
            "kind": "m8_duckdb_offline_rules_replay_no_jev_calls",
            "split": split,
            "case_sha256": manifest["case_sha256"],
            "duckdb_version": duckdb.__version__,
            "rows": len(rows),
            "scoring": scoring,
            "sql_preview": sql_preview(),
            "limit": "Python rules classify rows read from DuckDB; Jev SQL was not executed.",
        }
        return report
    finally:
        connection.close()


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Bounded DuckDB routing-table exercise")
    parser.add_argument("--project", type=Path, default=Path.cwd())
    parser.add_argument("--split", choices=("dev", "test"), default="test")
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        report = offline_replay(args.project, args.split, args.database)
        _write(args.output, report)
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0
    except (OSError, ValueError, duckdb.Error) as exc:
        parser.exit(1, f"DuckDB routing exercise: {exc}\n")


if __name__ == "__main__":
    raise SystemExit(main())
