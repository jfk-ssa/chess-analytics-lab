# Learning opening strategy through transpositions

**HTML version:** [Open the interactive learning page](https://jfk-ssa.github.io/chess-analytics-lab/transpositions.html).

Decision recorded: October 9, 2026. Status: checked training-game corpus plus research and integration design. The full Chess Analytics Lab repository has been relocated into the linked project folder. The game selection is implemented; opening-position models and training exercises described here are proposed work. The HTML board walkthrough is a legal, illustrative example.

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

Start with White using public games. Rank eligible White decision positions by frequency in the declared corpus, then choose a small opening family with useful convergence. Extend the same analysis and lesson format to Black after the White workflow is useful. The owner prefers a richer reference corpus of quality games rather than their personal history.

### Rating floor and reference quality

Require **both players to have known ratings of at least 1000**. A game with one player below 1000 is excluded, even if its average rating is higher. Ratings exactly 1000 are included; the inventory separately reports strict `>1000` counts. These are Lichess performance ratings recorded in PGN `WhiteElo` and `BlackElo`, not interchangeable FIDE ratings.

The default reference cohort is [Lichess Elite Database](https://database.nikonoel.fr/). Since December 2021, its publisher selects standard games between players rated 2500+ and 2300+, excluding bullet. We independently enforce a 2300 floor for both players, at least one player at 2500, and no Bullet event in the Elite reference selection. This provides stronger opening examples without treating every highly rated move as correct.

The broader public comparison cohort retains the 1000 floor. For both cohorts, require a completed result and at least 20 half-moves, exclude marked bots, and preserve source and time-control context. Historical January 2013 games remain in the inventory but are excluded from the current training selection. Unknown ratings and shorter games are excluded from training. Excluding marked bots does not prove every remaining account is human.

Keep the Elite and broader cohorts separate when calculating opening frequencies. Elite choices describe strong online play; the broader cohort describes the observed public sample. Neither is the user's personal encounter frequency, and neither establishes a best move by win rate alone.

The full lab already retains move-rich PGNs and checked snapshots. The earlier 174-game `thibault` example belongs to a separate companion case study, not the main lab's analytical corpus.

The checked combined inventory contains **1,295,879 unique accepted games** from eleven sources. Both players are rated at least 1000 in **1,232,182** games; both are strictly above 1000 in **1,231,872**. The completed, non-marked-bot, at-least-20-ply training selection contains **1,042,346** games. There are 218 games missing at least one rating; they are excluded from training.

| Source group | Retained games | Training games |
|---|---:|---:|
| November 2025 Elite month | 278,481 | 240,086 |
| Nine recent public prefixes, December 2025–August 2026 | 896,066 | 802,260 |
| January 2013 historical foundation | 121,332 | 0 |
| **Unique combined corpus** | **1,295,879** | **1,042,346** |

Deduplication by provider and game ID found no overlapping accepted games across these sources. Elite covers November 1–30; each general-public prefix covers the first day of its month. The HTML corpus panel reads exact reconciled totals and per-source windows from [the checked opening corpus report](../reports/opening-corpus.json). The [pre-expansion rating inventory](../reports/retained-rating-inventory.json) preserves the earlier counts before Elite was added.

The August analytical publication separately contains 330,956 moves from 4,924 hash-selected games, including ten zero-ply selections. This historical clock-analysis sample is not the opening corpus. The opening game index points to retained, legally validated full PGNs; deriving the first 20 plies of each selected game is the next step. See [data sources](DATA_SOURCES.md) and [M3 coverage](../reports/M3-coverage.json).

Initially rank White-to-move positions within a declared rating/time-control cohort from the public sources. Personal weighting is optional future work; the current corpus does not require a personal account.
Use all moves by both players to reconstruct the routes. For White training, use White-to-move decision positions. When a personal account is selected, also filter to games where that account is White. Black replies remain part of those lessons because they determine which position White faces next. Black training later uses the corresponding learner-color filter; it must not assume that a color-swapped position preserves chess meaning.

Frequency is the first ranking criterion. Count distinct games that reach a position, divided by all eligible games in the declared source/cohort and learner color. Count a game once per position even if the position repeats. Report the counts and window alongside every rate.

Within similarly frequent candidates, favor positions that join multiple meaningful routes and expose useful strategic choices. Once training results exist, observed recognition failures and decision errors can help order lessons. Avoid combining these signals into an opaque score in the first version.

An alternative policy, `most_frequent`, can rank candidates across both learner colors. Keep this policy separate from the default `white_first`: the user's initial preference remains White, and a slightly more frequent Black scenario should not silently override it. Frequency describes the chosen corpus and time window, not all chess players.

## Getting more games

The [November 2025 Elite file](https://database.nikonoel.fr/lichess_elite_2025-11.zip) has been downloaded in full. The retained ZIP is 80,347,217 bytes; its PGN is 267,557,755 bytes and contains 280,246 records. It covers the curated month rather than an ordered first-day prefix. The publisher listing currently ends at November 2025. The retained receipt contains locally computed SHA256 hashes, which identify the downloaded bytes; no publisher checksum is claimed.

Elite preserves game URLs in `LichessURL` rather than the lab's expected `Site` tag and omits clock annotations. A versioned adapter restores `Site` from `LichessURL` before the existing ingestion pipeline validates legal moves, records dispositions, and publishes immutable game/player snapshots. The original ZIP and PGN are retained. This source supports opening study; absent clocks cannot support clock-pressure analysis.

The corpus builder also reuses all nine retained recent monthly sources, expanding well beyond the original August 5% move selection. It checks source/snapshot hashes, deduplicates by provider and game ID, rejects conflicting metadata, and publishes a filtered game index in Parquet and DuckDB. Full legal PGNs remain in their existing locations and are linked by source file, snapshot ID, and ordinal; creating another full PGN copy of the combined corpus is unnecessary.

Reproduce the manual acquisition and corpus build from the repository root:

```sh
uv run --locked --no-editable python scripts/acquire_elite.py
uv run --locked --offline --no-editable python scripts/ingest_elite.py
uv run --locked --offline --no-editable python scripts/build_opening_corpus.py
```

Keep installed documentation/dashboard/dbt extras in these commands if needed. [Selection configuration](../config/opening-corpus.json) records the rating policy, pinned retained snapshot paths, source URL, and resource limits. Acquisition is explicit, never triggered by an import, the website, or a drill. Later Elite months can be added through a new versioned source plan when they are published.

For broader coverage, the [Lichess open database](https://database.lichess.org/) provides monthly standard rated archives containing billions of games across its history. A longer chronological prefix still emphasizes the beginning of a month. A representative month sample would require a declared sampling plan over a broader scan, with storage and processing limits recorded before acquisition. Keep every new source and extraction plan versioned; preserve the existing benchmark snapshots.

For optional personal practice later, the [player game export API](https://lichess.org/api#tag/Games/operation/apiGamesUser) or an uploaded PGN history can supply encounter frequency. The current public reference corpus does not depend on these sources.

Other development-month prefixes already retained in the lab are documented in [M7](M7.md). Inspect their provenance before selecting or combining them. Report each source's accepted games, replay coverage, and date range separately; do not add corpus counts and call the result unique games without deduplication.

### Storage and operating cost

The source download and local processing do not require model API calls or a hosted database. Storage and CPU time are the immediate costs. The Elite archive expands from about 80 MB to 268 MB; its compatible PGN, ingestion artifacts, DuckDB snapshot, and Parquet files add local working copies. The configured 8 GB allowance bounds this import's workspace, including retained attempts; it is not a predicted final database size. The combined corpus builder requires 3 GB of free disk before indexing and caps DuckDB at 1 GB of memory and 2 GB of temporary disk. Deduplication aggregates game keys before joining full metadata, avoiding a sort of every full record.

Measured after publication, the new index is 141.8 MB in DuckDB plus 91.9 MB in Parquet, about **234 MB** combined. Retained PGN, compressed source, ZIP, JSONL, DuckDB, and Parquet artifacts across `data/` and `work/` total about **9.15 GB**, including working copies and retained failed attempts; DuckDB files account for about **1.40 GB**. These are measured local file sizes, not billed cloud storage.

Keep PGNs and full warehouses outside Git. Publish compact counts and manifests to the static website, and derive only the opening depth needed for analysis. One million games at 20 plies implies up to 20 million position visits before deduplication; storing all later board states would multiply the workload without helping the first opening lesson. That is a row-count illustration, not a measured storage estimate.

The existing public site can use [GitHub Pages on GitHub Free](https://docs.github.com/en/pages/getting-started-with-github-pages/what-is-github-pages). Standard GitHub-hosted Actions runners are [free for public repositories and Pages](https://docs.github.com/en/billing/concepts/product-billing/github-actions); artifact and cache storage have their own limits. Only the small static build is uploaded. A future hosted analytical service could introduce storage, compute, and transfer charges, so it should follow a measured need. Stockfish enrichment consumes local compute; paid model-generated lessons would need a separate explicit budget.

## Position identity and routes

Build a directed graph: positions are nodes, legal moves are edges, and each played game records a route through the graph. Matching positions join; route records preserve how each game got there. Repetitions can create cycles, so analytical summaries must use a depth window and must not assume every graph is a tree.

For standard chess, the opening position key includes piece placement, side to move, castling rights, and the en passant square only when an en passant capture is legal. Use a documented normalized representation before hashing, retain that representation with the key, and version the normalization rule. [Python-chess's FEN documentation](https://python-chess.readthedocs.io/en/latest/core.html#chess.Board.fen) describes these fields and legal en passant normalization.

Retain full FEN, half-move counters, and the game route separately. The opening key identifies a position for recognition and legal continuations; it does not encode all repetition or draw-claim history. Engine comparisons that depend on those rules must preserve the relevant history or declare their limitations.

An exact transposition and a similar pawn structure serve different lessons. Exact matching can share position analysis. A structure-based lesson can share strategic themes but must identify differences in piece placement and tactics. Opening names and ECO codes are descriptive labels and must not replace position identity.

## Reusing the existing pipeline and database

Reuse the existing bounded ingestion → legal PGN replay → immutable Parquet/DuckDB snapshot → optional dbt marts → analytics → checked publication workflow. Keep the versioned `warehouse.duckdb` snapshots and existing `fact_game`, `fact_player_game`, and sampled `fact_move` relations as the foundation. This work does not need another database engine.

The current [move extractor](../analytics_m3/moves.py) already records UCI moves, side, ply, clocks, and source evaluations for hash-selected accepted games. It does not record position keys or complete board states. Extend replay to emit opening visits and legal transitions, retaining the source/game IDs and snapshot lineage, rather than infer transpositions from opening tags.

Read a checked source snapshot and its retained PGNs; create a new derived opening snapshot with position/visit/edge Parquet files and corresponding DuckDB tables. Follow the lab's immutable publication and pointer-validation pattern. Original foundation and analytical snapshots must remain reproducible. Existing dbt models and analytical tools can join the new relations through provider/game IDs and explicit snapshot identity.

The checked opening-game index selects 1,042,346 games. An opening-only pass can process their first 20 plies without retaining every later move. Record that selection as a new extraction plan so it cannot be mistaken for the existing clock-analysis sample. Source evaluations are optional and sparse; transposition detection requires legal moves, not engine annotations.

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

1. Use the checked opening-game index and declare a White rating/time-control cohort; the default Elite selection is implemented. Use a personal game export later if personalized prioritization is requested.
2. Add visit, position, move, and continuation models to the existing databases. Compute White frequencies and transposition summaries before selecting an opening family.
3. Author a small set of shared-position lessons and route-specific exceptions, then produce a bounded map and drills.
4. Run the learning pilot and inspect recognition, move quality, time, and mistaken transfer.
5. Extend learner-color filtering and lessons to Black; compare with the optional most-frequent policy.

The relocated lab supplies the ingestion, legal replay, warehouse, corpus rating filters, and static documentation infrastructure. The checked game index is implemented. The next functional step is the derived position/visit/edge snapshot and measured White lesson ranking within the default Elite reference cohort.
