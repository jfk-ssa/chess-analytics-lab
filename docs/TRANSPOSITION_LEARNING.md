# Learning opening strategy through transpositions

Decision recorded: October 9, 2026. Status: research and integration design. The full Chess Analytics Lab repository has been relocated into the linked project folder. Opening models and training exercises described here are proposed work; the HTML walkthrough is a legal, illustrative example.

## Motivation

Learning many opening sequences can mean learning the same resulting position several times. A transposition map makes that shared material visible. Its learning unit is a recognizable position connected to candidate moves, strategic plans, tactical checks, and several routes by which it can arise.

The intended mental shortcut is: recognize a position, retrieve a small set of relevant candidates and their reasons, then check the current tactics. Recognition could reduce time spent reconstructing familiar opening analysis. Knowing a transposition alone does not establish a best move, and opponents can divert play before the shared position is reached.

For example, `1.d4 Nf6 2.c4 e6 3.Nf3 d5` and `1.d4 d5 2.c4 e6 3.Nf3 Nf6` reach the same opening position with White to move. A learner can study that position's candidates and plans once and practice recognizing it through both routes. Each route also needs coverage of important earlier alternatives.

There are three proposed benefits:

1. **Reuse:** one position lesson can serve multiple move sequences.
2. **Recognition:** varied routes can teach the learner to retrieve knowledge from the board position.
3. **Relevant practice:** match history can identify shared positions and branch points that the learner is likely to encounter.

These are design hypotheses. The amount of graph compression, improvement in recognition, and improvement in move decisions must be measured separately.

## Research support and its limits

| Primary source | Finding relevant to the design | Interpretation for this project |
|---|---|---|
| Chase & Simon (1973), [Perception in chess](https://doi.org/10.1016/0010-0285(73)90004-2) | Their chess perception and recall experiments developed an account of expertise based on meaningful groups of pieces, or chunks. | Learn meaningful board patterns alongside the moves they suggest. This paper does not test a transposition curriculum. |
| Gobet & Simon (1996), [Templates in Chess Memory](https://doi.org/10.1006/cogp.1996.0011) | Multiple-board recall experiments motivated a revised account that includes larger retrieval structures, or templates, alongside chunks. | Organizing related positions and reusable information has a cognitive rationale. The templates in this research are not equivalent to our graph nodes. |
| Bilalić, McLeod & Gobet (2009), [Specialization Effect and Its Influence on Memory and Problem Solving in Expert Chess Players](https://doi.org/10.1111/j.1551-6709.2009.01030.x) | Experts performed better on recall and problem solving within their opening specialization, despite comparable general skill. | Start with a bounded repertoire and connect recognition to actions and plans. This study examines expertise and familiarity; it does not establish that our training method will cause improvement. |

The strongest motivation is the link between familiar positions and knowledge of appropriate actions. A lesson should therefore explain why a candidate works, what the opponent threatens, and what changes would invalidate the plan. Recalling a board or naming an opening is insufficient evidence that a learner can choose a good move.

The sources support the proposed mechanism indirectly. None of these studies establishes that learning through transpositions is superior to conventional opening study. Our experiments should make that comparison explicitly and avoid promising rating gains from the graph alone.

## Initial scope and prioritization

Start with White. Rank eligible White decision positions by how often they occur in the selected cohort or player's match history, then choose a small opening family with useful convergence. Extend the same analysis and lesson format to Black after the White workflow is useful.

The full lab already retains move-rich PGNs and checked snapshots. The earlier 174-game `thibault` example belongs to a separate companion case study, not the main lab's analytical corpus.

| Retained source | Accepted games | What it supports |
|---|---:|---|
| Complete January 2013 archive | 121,332 | Historical pipeline foundation; not contemporary player behavior |
| August 2026 bounded prefix | 99,467 | Initial opening exploration; observed August 1 only |
| December 2025 bounded prefix | 99,307 | Separate retained analytical cohort; observed December 1 only |

These are separate corpora, not a deduplicated combined count. The August analytical publication contains 330,956 moves from 4,924 hash-selected games, including ten zero-ply selections. Its 5% move sample is adequate for a bounded pilot; we can also replay opening plies from the retained accepted-game PGNs without downloading more data. See [data sources](DATA_SOURCES.md) and [M3 coverage](../reports/M3-coverage.json).

Initially rank White-to-move positions within a declared rating/time-control cohort from a retained source. Personal recommendations require a chosen account or supplied history; archive cohort frequency is not an individual's repertoire frequency.
Use all moves by both players to reconstruct the routes. For White training, use White-to-move decision positions. When a personal account is selected, also filter to games where that account is White. Black replies remain part of those lessons because they determine which position White faces next. Black training later uses the corresponding learner-color filter; it must not assume that a color-swapped position preserves chess meaning.

Frequency is the first ranking criterion. Count distinct games that reach a position, divided by all eligible games in the declared source/cohort and learner color. Count a game once per position even if the position repeats. Report the counts and window alongside every rate.

Within similarly frequent candidates, favor positions that join multiple meaningful routes and expose useful strategic choices. Once training results exist, observed recognition failures and decision errors can help order lessons. Avoid combining these signals into an opaque score in the first version.

An alternative policy, `most_frequent`, can rank candidates across both learner colors. Keep this policy separate from the default `white_first`: the user's initial preference remains White, and a slightly more frequent Black scenario should not silently override it. Frequency describes the chosen corpus and time window, not all chess players.

## Getting more games

Start by replaying opening plies from the retained August PGNs. This expands the opening analysis beyond the current 5% move selection while reusing the existing 99,467 accepted-game source. More downloads are unnecessary for that first expansion.

For broader coverage, the [Lichess open database](https://database.lichess.org/) provides monthly standard rated archives containing billions of games across its history. A longer chronological prefix still emphasizes the beginning of a month. A representative month sample would require a declared sampling plan over a broader scan, with storage and processing limits recorded before acquisition. Keep every new source and extraction plan versioned; preserve the existing benchmark snapshots.

For personal practice, the [player game export API](https://lichess.org/api#tag/Games/operation/apiGamesUser) or an uploaded PGN history is a more relevant source. Include moves, record the account and observed date window, and rank the positions encountered in that history. A larger general archive cannot substitute for the learner's own match frequency.

Other development-month prefixes already retained in the lab are documented in [M7](M7.md). Inspect their provenance before selecting or combining them. Report each source's accepted games, replay coverage, and date range separately; do not add corpus counts and call the result unique games without deduplication.

## Position identity and routes

Build a directed graph: positions are nodes, legal moves are edges, and each played game records a route through the graph. Matching positions join; route records preserve how each game got there. Repetitions can create cycles, so analytical summaries must use a depth window and must not assume every graph is a tree.

For standard chess, the opening position key includes piece placement, side to move, castling rights, and the en passant square only when an en passant capture is legal. Use a documented normalized representation before hashing, retain that representation with the key, and version the normalization rule. [Python-chess's FEN documentation](https://python-chess.readthedocs.io/en/latest/core.html#chess.Board.fen) describes these fields and legal en passant normalization.

Retain full FEN, half-move counters, and the game route separately. The opening key identifies a position for recognition and legal continuations; it does not encode all repetition or draw-claim history. Engine comparisons that depend on those rules must preserve the relevant history or declare their limitations.

An exact transposition and a similar pawn structure serve different lessons. Exact matching can share position analysis. A structure-based lesson can share strategic themes but must identify differences in piece placement and tactics. Opening names and ECO codes are descriptive labels and must not replace position identity.

## Reusing the existing pipeline and database

Reuse the existing bounded ingestion → legal PGN replay → immutable Parquet/DuckDB snapshot → optional dbt marts → analytics → checked publication workflow. Keep the versioned `warehouse.duckdb` snapshots and existing `fact_game`, `fact_player_game`, and sampled `fact_move` relations as the foundation. This work does not need another database engine.

The current [move extractor](../analytics_m3/moves.py) already records UCI moves, side, ply, clocks, and source evaluations for hash-selected accepted games. It does not record position keys or complete board states. Extend replay to emit opening visits and legal transitions, retaining the source/game IDs and snapshot lineage, rather than infer transpositions from opening tags.

Read a checked source snapshot and its retained PGNs; create a new derived opening snapshot with position/visit/edge Parquet files and corresponding DuckDB tables. Follow the lab's immutable publication and pointer-validation pattern. Original foundation and analytical snapshots must remain reproducible. Existing dbt models and analytical tools can join the new relations through provider/game IDs and explicit snapshot identity.

A first pilot can reuse the existing 5% move-game selection. A broader opening-only pass can process the first 20 plies of all accepted retained PGNs without retaining every later move. Record that selection as a new extraction plan so it cannot be mistaken for the existing clock-analysis sample. Source evaluations are optional and sparse; transposition detection requires legal moves, not engine annotations.

Python-chess is already pinned at 1.11.2. Use it for legal replay and canonical position generation; DuckDB/dbt handles aggregation and joins. Record source/snapshot hashes, parser and position-key versions, depth cutoff, inclusion rules, and build configuration in the derived manifest. Extend the versioned metric contracts and publication checks before exposing graph statistics through the dashboard or analyst.

| Proposed relation | Grain | Purpose |
|---|---|---|
| `chess_game_positions` | source snapshot ID × provider × game ID × ply, including ply 0 | Preserve board states, routes, and repetition context for each game |
| `chess_positions` | position-key version × position ID | Store normalized position, side to move, and descriptive labels |
| `chess_game_moves` | source snapshot ID × provider × game ID × ply, starting at ply 1 | Record from-position, legal move, and to-position |
| `chess_position_continuations` | opening snapshot ID × cohort ID × learner color × position ID × move | Summarize observed choices, denominators, and results |
| `chess_transposition_summary` | opening snapshot ID × cohort ID × learner color × position ID × analytical depth window | Count visits, distinct arrival routes, and route coverage |
| `chess_training_attempts` | attempt ID | Record lesson version, presented route, response, accuracy, and time |

These are proposed relations, not implemented tables. Follow [the existing architecture](ARCHITECTURE.md), [metric contracts](METRICS.md), and checked analytical publication pattern. Add an opening snapshot contract and its own validated pointer rather than modifying a frozen analytical publication in place. The existing numerical and classifier reference cases retain their original data identities and claims.
Training attempts are new observations with their own schema and retention policy; they should not be treated as game-source data. They can use a separately managed relation alongside the same DuckDB/Parquet analytics, with a later storage decision if concurrent writes become necessary. A graph database is unnecessary for the first version: node, edge, and visit tables are sufficient, and the interface can receive a bounded graph extract.

The [Lichess opening explorer](https://github.com/lichess-org/lila-openingexplorer#public-http-api) provides position-based statistics that could supplement the selected history. Cache and label those observations with their own filters and retrieval times. They provide comparative context and do not replace the captured game routes.

## Analytics and lessons

Begin with the first 20 half-moves, or ten complete moves, and keep this cutoff configurable. Exclude the initial position and trivial early shared prefixes when choosing transposition lessons. A candidate depth floor of six half-moves is a starting policy to inspect, not a finding about when useful learning begins.

Calculate sequence-to-position compression at each fixed depth. If S distinct UCI move prefixes produce P distinct normalized positions at that depth, `1 - P/S` describes the reduction in distinct endpoint representations. Shared prefixes do not count as transpositions; repeats of one sequence do not increase S. Examine repetition-related convergence separately so reversible move loops do not inflate the apparent learning benefit.

Also report distinct arrival routes, distinct game visits, common departures, and how much of the selected history the lesson set covers. Coverage means the share of eligible games that encounter at least one selected lesson position within the depth window. Overlapping lesson visits must not be summed as if they were different games.

Candidate-move statistics describe observed play. Full-game results can be influenced by ratings, time control, later mistakes, and sample selection. Display sample counts and keep engine assessments separate, with engine version and analysis settings. Frequency can identify useful practice; win rate alone cannot identify the best move or prove the value of an opening route.

Each lesson should contain a board position, example arrival routes, candidate moves with reasons, the opponent's immediate threats, typical pawn breaks and plans, important earlier deviations, and an explanation of when the position resembles another lesson but needs a different action. Curated strategic explanations and candidate validation are part of the lesson authoring work.

Practice should alternate recognition from a complete route, recognition from the board alone, choosing and explaining a continuation, and detecting a nearby position where the usual plan fails. Both players influence the route: a training map must show common exits instead of implying a learner can force every destination.

## How to evaluate the hypothesis

Measure three outcomes separately: correct position recognition, quality of the chosen move and explanation, and decision time. Faster responses are useful only if decision quality is maintained or improved. A predefined set of acceptable candidates is preferable to treating one engine move as the only valid answer in quiet opening positions.

Compare a position-and-transposition lesson format with a sequence-focused format using equal study time and comparable material. For a single learner, use matched lesson groups, randomize assignment where feasible, and counterbalance the order. Prior exposure and carryover limit causal conclusions, so report this as a personal pilot.

Withhold some arrival sequences during instruction and test whether the learner recognizes their shared positions. Include a separate set of similar-but-different boards to measure mistaken transfer, plus delayed checks to assess retention. Separate game data used to select lessons from later games used to assess repertoire coverage. Distinct games must remain distinct, and route leakage across training and test sets should be documented.

Opening decision time from a game clock requires careful treatment of increments, missing observations, and network delay. Controlled drill response times provide a cleaner initial measure. Changes in game results are a secondary descriptive outcome and cannot alone establish that the lessons worked.

## Next implementation sequence

1. Select a retained analytical source and declared White rating/time-control cohort; validate replay and snapshot provenance. Use a personal game export later if personalized prioritization is requested.
2. Add visit, position, move, and continuation models to the existing databases. Compute White frequencies and transposition summaries before selecting an opening family.
3. Author a small set of shared-position lessons and route-specific exceptions, then produce a bounded map and drills.
4. Run the learning pilot and inspect recognition, move quality, time, and mistaken transfer.
5. Extend learner-color filtering and lessons to Black; compare with the optional most-frequent policy.

The relocated lab already supplies the ingestion, legal replay, warehouse, cohort filters, and static documentation infrastructure. The next functional step is the derived opening snapshot and measured White lesson ranking.
