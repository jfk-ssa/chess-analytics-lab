"""Regenerate the two M4 memos and their exact figure inputs."""

import json
from pathlib import Path

from chess_analytics.common import write_json
from chess_analytics.dashboard.analysis import (
    clock_analysis,
    coverage,
    current_snapshot,
    opening_comparison,
)

PROJECT = Path(__file__).resolve().parents[1]


def pct(value):
    return "n/a" if value is None else f"{100 * value:.1f}%"


def build(project=PROJECT):
    snapshot = current_snapshot(project)
    source = coverage(project, snapshot)
    opening = opening_comparison(project, snapshot)
    clock = clock_analysis(project, snapshot)
    report = {
        "kind": "deterministic descriptive figures; no model response",
        "analytical_id": source["analytical_id"],
        "coverage": source,
        "opening": opening,
        "clock": clock,
    }
    write_json(project / "reports/M4-figures.json", report)
    first, second = opening["families"].values()
    names = list(opening["families"])
    first_interval = first["adjusted_95pct_cluster_bootstrap_interval"]
    second_interval = second["adjusted_95pct_cluster_bootstrap_interval"]
    retained = opening["retained_player_games_with_opponent_rating"]
    opening_text = f"""# Memo 1 — Opening score in one observed cohort

**Question.** How did Black's score rate compare for {names[0]} and {names[1]}
among players rated 1400–1599 at exactly 60+0?

**Method.** Use completed non-marked-bot games in analytical snapshot
`{source["analytical_id"]}`. Score is wins plus half draws, divided by player-games.
For a descriptive adjustment, restrict to games with opponent ratings, split
player-minus-opponent rating into below −100, −100 to 99, and 100+ strata, then
weight both openings by the same pooled stratum distribution. The interval is a
seeded 400-repetition focal-player cluster bootstrap over this observed cohort.

**Result.** {names[0]}: {first["raw"]["wins"]} wins, {first["raw"]["draws"]} draws,
{first["raw"]["losses"]} losses in {first["raw"]["eligible_player_games"]} games;
score rate {pct(first["raw"]["score_rate"])}. {names[1]}:
{second["raw"]["wins"]} wins, {second["raw"]["draws"]} draws,
{second["raw"]["losses"]} losses in {second["raw"]["eligible_player_games"]} games;
score rate {pct(second["raw"]["score_rate"])}. Adjusted score rates are
{pct(first["adjusted_score_rate"])} (bootstrap interval
{pct(first_interval[0])}–{pct(first_interval[1])})
and {pct(second["adjusted_score_rate"])} (interval
{pct(second_interval[0])}–{pct(second_interval[1])}), respectively.
All three rating-difference strata are represented; {retained}
player-games entered the common-weight comparison.

**Interpretation.** These differences are small relative to within-prefix
uncertainty. They do not show that choosing either opening changes outcomes.
The ordered archive prefix covers only 2026-08-01, opening labels are source
tags, and player experience/opponent behavior may confound the comparison.
Bootstrap intervals reflect player clustering within this prefix, not uncertainty
from sampling the whole month. Opponent dependence remains unmodeled.

**What would change the conclusion.** A broader date sample, repeated-player
coverage, stronger controls for opponent and position, and stable results across
time controls would be needed before a general claim.

Reproduce: `PYTHONPATH=. .venv/bin/python scripts/build_m4_report.py`.
Exact inputs: [M4 figures](../reports/M4-figures.json).
"""
    lines = []
    for bucket in clock["buckets"]:
        lines.append(
            f"| {bucket['bucket']} | {bucket['eligible_moves']:,} | "
            f"{bucket['evaluable_moves']:,} | {pct(bucket['evaluation_coverage'])} | "
            f"{bucket['proxy_errors']:,}/{bucket['evaluable_moves']:,} | "
            f"{pct(bucket['error_proxy_rate'])} |"
        )
    clock_text = f"""# Memo 2 — Clock pressure and evaluation coverage

**Question.** What can the source evaluations say about the >=200 cp
deterioration proxy as pre-turn clock time falls?

**Method.** Use snapshot `{source["analytical_id"]}`. Games are selected by
game-ID hash within the August 1 prefix, independently of annotation presence.
Only completed, non-marked-bot zero-increment games and moves after a player's
first recorded clock are eligible. The previous same-player clock defines the
pre-turn bucket. Comparable centipawn evaluations define the rate denominator;
mate transitions and missing evaluations are excluded from it. A separate
stratified table by exact time control, rating band and phase is in the figures.

| Clock before turn | Eligible | Evaluable | Coverage | Proxy errors / evaluable | Proxy rate |
|---|---:|---:|---:|---:|---:|
{chr(10).join(lines)}

**Interpretation and uncertainty.** The under-10-second bucket has the largest
observed proxy rate, but its evaluation coverage is only
{pct(clock["buckets"][0]["evaluation_coverage"])}. Annotation availability is
selected, moves within a game are dependent, and player strength, game phase and
position may vary by bucket. No independent-move confidence interval or causal
time-pressure effect is claimed. This is an exploratory source-evaluation proxy,
not an official Lichess blunder label. The ordered source prefix covers only
2026-08-01; no monthly estimate follows.

**What would change the conclusion.** A predeclared position sample evaluated
with one fixed engine configuration, broader dates, and sensitivity checks for
the deterioration threshold and player/game strata would reduce the main
selection and measurement concerns.

Reproduce: `PYTHONPATH=. .venv/bin/python scripts/build_m4_report.py`.
Exact inputs: [M4 figures](../reports/M4-figures.json).
"""
    (project / "docs/M4-OPENINGS.md").write_text(opening_text)
    (project / "docs/M4-CLOCK.md").write_text(clock_text)
    return {
        "analytical_id": source["analytical_id"],
        "memo_count": 2,
        "figure_file": "reports/M4-figures.json",
        "clock_strata": len(clock["strata"]),
    }


if __name__ == "__main__":
    print(json.dumps(build(), indent=2))
