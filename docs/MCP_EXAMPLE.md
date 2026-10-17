# Worked example on the real August prefix

On 2026-10-17 a local MCP client called `chesslab mcp` against the analytical
snapshot in that machine's `data/` directory. The dataset ID is
`84a38a404815ed2729917d76`. The source snapshot ID is
`6cf51473f8da6ae6b12ea5c2`. A second independent run produced the same
evidence IDs.

The synthetic demo is a different snapshot: 6 seen games, and a draw rate of
0.25 on 4 eligible games. The five steps below were answered from this
August prefix. Each step names the tool, the arguments, and the raw JSON
result. Every result includes the dataset ID and an evidence ID.

The games are not in this repository. These figures are the recorded tool
output. They were not recomputed for this note.

## 1. `get_dataset_coverage`

Arguments:

```json
{}
```

Result:

```json
{
  "dataset_id": "84a38a404815ed2729917d76",
  "evidence_id": "ev_c48b3bdc248ad2828830",
  "result": {
    "analytical_id": "84a38a404815ed2729917d76",
    "move_coverage": {
      "after_clock_moves": 330585,
      "before_clock_moves": 320783,
      "cp_eval_moves": 32135,
      "mate_eval_moves": 2005,
      "moves": 330956,
      "selected_games": 4914
    },
    "observed_dates": {
      "first_utc_date": "2026-08-01",
      "last_utc_date": "2026-08-01",
      "missing": {
        "participant_rating": 0,
        "played_at": 0,
        "source_opening": 0,
        "utc_date": 0
      }
    },
    "opening_coverage": {
      "eligible_games": 99117,
      "known_opening_games": 99117,
      "missing_source_opening": 0
    },
    "partial_archive": true,
    "selection": {
      "move_rows": 330956,
      "selected_games": 4924,
      "selected_zero_ply_games": 10,
      "selection": "SHA256(game_id) first 8 bytes mod 20 == 0"
    },
    "source_counts": {
      "accepted": 99467,
      "conflict": 0,
      "duplicate": 0,
      "excluded": 533,
      "quarantine": 0,
      "seen": 100000
    },
    "source_kind": "bounded_standard_rated_prefix",
    "source_snapshot_id": "6cf51473f8da6ae6b12ea5c2"
  }
}
```

The snapshot is one UTC day, 2026-08-01, and `partial_archive` is true:
100,000 games seen, 99,467 accepted, and 99,117 eligible. The hash selection
counts 4,924 games, 10 of them with zero plies, so move coverage lists 4,914.

## 2. `query_metric` for `game_draw_rate`

Arguments:

```json
{
  "metric_id": "game_draw_rate",
  "filters": {}
}
```

Result:

```json
{
  "dataset_id": "84a38a404815ed2729917d76",
  "evidence_id": "ev_210138076071bf2b7e50",
  "result": {
    "analytical_id": "84a38a404815ed2729917d76",
    "contract_sha256": "b119f02815e73adbe680120b2b26460cd2f5cf867dd0399d1642b560e29042e4",
    "denominator": 99117,
    "metric_id": "game_draw_rate",
    "numerator": 3669,
    "value": 0.037016858863767065,
    "version": "1.0.0"
  }
}
```

3,669 of the 99,117 eligible games are draws. The evidence ID on this
snapshot is `ev_210138076071bf2b7e50`.

## 3. Opening comparison

### Grouped `opening_usage`

Arguments:

```json
{
  "metric_id": "opening_usage",
  "filters": {},
  "group_by": [
    "opening_family"
  ]
}
```

Result, an excerpt of 110+ rows: the first 5 of 138. The recorded result
has `"truncated": false`. The denominator and the evidence ID are the
recorded values:

```json
{
  "dataset_id": "84a38a404815ed2729917d76",
  "evidence_id": "ev_d304a304c2338d7d3106",
  "result": {
    "analytical_id": "84a38a404815ed2729917d76",
    "denominator": 99117,
    "group_by": [
      "opening_family"
    ],
    "metric_id": "opening_usage",
    "rows": [
      {
        "family": "Sicilian Defense",
        "numerator": 9985,
        "value": 0.10073953005034454
      },
      {
        "family": "Queen's Pawn Game",
        "numerator": 9415,
        "value": 0.09498875066840198
      },
      {
        "family": "French Defense",
        "numerator": 6027,
        "value": 0.06080692514906626
      },
      {
        "family": "Caro-Kann Defense",
        "numerator": 5981,
        "value": 0.06034282716385685
      },
      {
        "family": "Scandinavian Defense",
        "numerator": 5187,
        "value": 0.05233209237567723
      }
    ]
  }
}
```

Sicilian Defense and Queen's Pawn Game are the two largest families in the
prefix, 9,985 and 9,415 of 99,117 eligible games.

### `compare_openings`

Arguments:

```json
{
  "filters": {
    "families": [
      "Sicilian Defense",
      "Queen's Pawn Game"
    ],
    "color": "white",
    "rating_min": 0,
    "rating_max_exclusive": 4000,
    "base_seconds": 300,
    "increment_seconds": 0
  }
}
```

Result:

```json
{
  "caveats": [
    "observed_prefix_only",
    "association_not_causation"
  ],
  "dataset_id": "84a38a404815ed2729917d76",
  "evidence_id": "ev_4b419f674d7421543c72",
  "result": {
    "caveats": [
      "observed_prefix_only",
      "association_not_causation"
    ],
    "dataset_id": "84a38a404815ed2729917d76",
    "families": [
      {
        "analytical_id": "84a38a404815ed2729917d76",
        "contract_sha256": "cdf817e41cb971eec2ae862f399daa4101f06d671fb01b45ad23ab1fbfbbf779",
        "draws": 49,
        "eligible_player_games": 1043,
        "filters": {
          "base_seconds": 300,
          "color": "white",
          "family": "Sicilian Defense",
          "increment_seconds": 0,
          "rating_max_exclusive": 4000,
          "rating_min": 0
        },
        "losses": 483,
        "low_support": false,
        "metric_id": "opening_player_score",
        "scope": "descriptive observed prefix; no causal claim",
        "score_rate": 0.5134228187919463,
        "version": "1.0.0",
        "win_rate": 0.4899328859060403,
        "wins": 511
      },
      {
        "analytical_id": "84a38a404815ed2729917d76",
        "contract_sha256": "cdf817e41cb971eec2ae862f399daa4101f06d671fb01b45ad23ab1fbfbbf779",
        "draws": 45,
        "eligible_player_games": 1046,
        "filters": {
          "base_seconds": 300,
          "color": "white",
          "family": "Queen's Pawn Game",
          "increment_seconds": 0,
          "rating_max_exclusive": 4000,
          "rating_min": 0
        },
        "losses": 493,
        "low_support": false,
        "metric_id": "opening_player_score",
        "scope": "descriptive observed prefix; no causal claim",
        "score_rate": 0.5071701720841301,
        "version": "1.0.0",
        "win_rate": 0.48565965583174,
        "wins": 508
      }
    ],
    "score_rate_difference_first_minus_second": 0.006252646707816223,
    "win_rate_difference_first_minus_second": 0.004273230074300305
  }
}
```

The client chose White, ratings from 0 to under 4000, and 300+0
(`base_seconds` 300, `increment_seconds` 0). No tool lists valid time
controls, so the client supplied that cohort itself. Listing time controls
remains a future idea.

The score-rate difference is about 0.006, on 1,043 Sicilian games and 1,046
Queen's Pawn games. The tool returns no confidence interval, so this
difference should not be read as a finding. The caveats on the result are
`observed_prefix_only` and `association_not_causation`.

## 4. Clock pressure

### `analyze_clock_pressure` for `under_10`

Arguments:

```json
{
  "bucket": "under_10"
}
```

Result:

```json
{
  "dataset_id": "84a38a404815ed2729917d76",
  "evidence_id": "ev_171900992a38ecdfb137",
  "result": {
    "analytical_id": "84a38a404815ed2729917d76",
    "bucket": "under_10",
    "contract_sha256": "0ee7dbc7a903dabbc22414ed0ac6623067053b55d8cf8c2e0bdcfa711c9698d8",
    "coverage_contract_sha256": "c52c72036d9796c6a0dabefc60ea68c3fa852023b1e2555f3f5361c9b397f1bc",
    "eligible_moves": 20978,
    "error_proxy_rate": 0.19311502938706968,
    "evaluable_moves": 1191,
    "evaluation_coverage": 0.05677376298979884,
    "mate_transition_moves": 369,
    "metric_id": "clock_pressure_error_proxy",
    "proxy_errors": 230,
    "scope": "exploratory source-evaluation proxy in sampled games of observed prefix",
    "version": "1.0.0"
  }
}
```

### `compare_clock_buckets`, `under_10` against `60_plus`

Arguments:

```json
{
  "first": "under_10",
  "second": "60_plus"
}
```

Result:

```json
{
  "caveats": [
    "source_evaluation_selection",
    "exploratory_proxy"
  ],
  "dataset_id": "84a38a404815ed2729917d76",
  "evidence_id": "ev_d24a979f2d4714389ae5",
  "result": {
    "buckets": [
      {
        "analytical_id": "84a38a404815ed2729917d76",
        "bucket": "under_10",
        "contract_sha256": "0ee7dbc7a903dabbc22414ed0ac6623067053b55d8cf8c2e0bdcfa711c9698d8",
        "coverage_contract_sha256": "c52c72036d9796c6a0dabefc60ea68c3fa852023b1e2555f3f5361c9b397f1bc",
        "eligible_moves": 20978,
        "error_proxy_rate": 0.19311502938706968,
        "evaluable_moves": 1191,
        "evaluation_coverage": 0.05677376298979884,
        "mate_transition_moves": 369,
        "metric_id": "clock_pressure_error_proxy",
        "proxy_errors": 230,
        "scope": "exploratory source-evaluation proxy in sampled games of observed prefix",
        "version": "1.0.0"
      },
      {
        "analytical_id": "84a38a404815ed2729917d76",
        "bucket": "60_plus",
        "contract_sha256": "0ee7dbc7a903dabbc22414ed0ac6623067053b55d8cf8c2e0bdcfa711c9698d8",
        "coverage_contract_sha256": "c52c72036d9796c6a0dabefc60ea68c3fa852023b1e2555f3f5361c9b397f1bc",
        "eligible_moves": 118217,
        "error_proxy_rate": 0.08331343996180472,
        "evaluable_moves": 12567,
        "evaluation_coverage": 0.10630450781190523,
        "mate_transition_moves": 897,
        "metric_id": "clock_pressure_error_proxy",
        "proxy_errors": 1047,
        "scope": "exploratory source-evaluation proxy in sampled games of observed prefix",
        "version": "1.0.0"
      }
    ],
    "caveats": [
      "source_evaluation_selection",
      "exploratory_proxy"
    ],
    "dataset_id": "84a38a404815ed2729917d76",
    "error_proxy_rate_difference_first_minus_second": 0.10980158942526495,
    "evaluation_coverage_difference_first_minus_second": -0.04953074482210639
  }
}
```

Under 10 seconds the proxy error rate is 0.19311502938706968 (230 of 1,191
evaluable moves). At 60 seconds or more it is 0.08331343996180472 (1,047 of
12,567). The evaluation-coverage difference, `under_10` minus `60_plus`, is
-0.04953074482210639. Coverage is lower under 10 seconds, so the comparison
is exploratory.

`analyze_clock_pressure` returns no caveats array. Its scope is
`exploratory source-evaluation proxy in sampled games of observed prefix`.
`compare_clock_buckets` returns these caveats:

```json
[
  "source_evaluation_selection",
  "exploratory_proxy"
]
```

## 5. Does clock pressure cause players to blunder?

No causal claim is supported. The definition tool returns the caveats below,
quoted as the tool returned them.

Tool: `get_metric_definition`

Arguments:

```json
{
  "metric_id": "clock_pressure_error_proxy"
}
```

Caveats:

```json
[
  "Exploratory proxy, not an official Lichess blunder label.",
  "Existing evaluation coverage is selected and source quality varies.",
  "The prefix and move sample do not represent all August games; no causal time-pressure claim."
]
```

Result:

```json
{
  "dataset_id": "84a38a404815ed2729917d76",
  "evidence_id": "ev_ac4b7789842497559262",
  "result": {
    "contract_sha256": "0ee7dbc7a903dabbc22414ed0ac6623067053b55d8cf8c2e0bdcfa711c9698d8",
    "dataset_id": "84a38a404815ed2729917d76",
    "definition": {
      "buckets_seconds": [
        "[0,10)",
        "[10,30)",
        "[30,60)",
        "[60,infinity)"
      ],
      "caveats": [
        "Exploratory proxy, not an official Lichess blunder label.",
        "Existing evaluation coverage is selected and source quality varies.",
        "The prefix and move sample do not represent all August games; no causal time-pressure claim."
      ],
      "coverage_denominator": "all eligible moves in bucket",
      "denominator": "evaluable eligible moves in bucket",
      "deterioration": "max(0, mover-perspective cp_before minus cp_after); source cp scores are White-perspective, invert both for Black",
      "eligible": "non-first move by a player in a zero-increment rated Standard game with valid prior same-player clock and a completed result, excluding source-marked bots",
      "evaluable": "eligible move with source-provided before and after centipawn evaluations; mate transitions excluded and counted separately",
      "grain": "one selected game x ply, stratified by clock-before bucket",
      "id": "clock_pressure_error_proxy",
      "null_rules": "first same-player move, missing/invalid clock, missing evaluations and mate transitions never become zero error",
      "numerator": "evaluable eligible moves with deterioration >= 200 centipawns",
      "sampling": "game ID SHA256 first eight bytes modulo 20 equals zero; deterministic 5% selection from the bounded prefix, independent of annotations",
      "units": "fraction",
      "version": "1.0.0"
    }
  }
}
```

## Scope and limits

> One UTC day, 2026-08-01. `partial_archive` is true. The source is a bounded
> prefix of 100,000 seen games: 99,467 accepted and 99,117 eligible.
> Move-level metrics use a deterministic 5% hash selection (4,924 selected
> games). The prefix is a convenience sample, not a population sample. The
> clock proxy is not a Lichess blunder label.

## Reproduce it

Point `--project` at the directory that contains the analytical snapshot.
Use the repository root when `data/analytical-moves-current.json` exists.
The analytical sequence in the [runbook](RUNBOOK.md) builds it:
`python -m chess_analytics.corpus`, then `acquire`, `extract`, `ingest`,
`moves`, and `report`. [Data sources](DATA_SOURCES.md) records the prefix
pin and the observed coverage. The games stay outside Git.

Without that snapshot, `--project` is the synthetic demo written by
`chesslab demo --scope all` under `work/portfolio-demo/project`. On that
snapshot the draw rate is 0.25. [The demo guide](DEMO.md) lists the fixture
counts. [The MCP guide](MCP.md) shows the client configuration. Replace
every path below with a local absolute path.

```sh
uv run --locked --offline --no-editable --extra mcp \
  --directory /absolute/path/to/chess-analytics-lab \
  chesslab --project /absolute/path/to/chess-analytics-lab mcp
```

For the synthetic demo, set `--project` to
`/absolute/path/to/chess-analytics-lab/work/portfolio-demo/project`.

Run the client as a local agent on the machine that holds the data. A cloud
agent cannot start a local stdio server and cannot see gitignored data.
Tell the agent to use only the chesslab MCP tools, and not to run terminal
commands or read repository files. A client that can use the shell may
rebuild the synthetic demo and report 0.25.

Those two setup mistakes account for three attempts. This is the prompt that
then succeeded:

```text
Use only the chesslab MCP server's tools. Do not run terminal commands or read repo files. Call get_dataset_coverage, then query_metric with metric_id game_draw_rate and filters {}. Report dataset_id and evidence_id from the results.
```

Evidence IDs depend on the snapshot. A reader with a different snapshot gets
different IDs. Two runs on this snapshot produced the IDs above. Matching
IDs show that the dataset, tool, arguments, and result hashed the same way.
They are not an independent proof that the metric is correct.
