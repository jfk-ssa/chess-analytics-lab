# Documentation website runbook

The public documentation homepage is
[Chess Analytics Lab](https://jfk-ssa.github.io/chess-analytics-lab/).
Markdown stays the maintained source; HTML adds navigation, interactive learning
examples and a browser-rendered version of the existing comparison report.
The site is static: it cannot run the analyst, contact a model or download games.

## What to read and what to maintain

| Published page | Maintained sources | What HTML adds |
| --- | --- | --- |
| [Homepage](https://jfk-ssa.github.io/chess-analytics-lab/) | [Portfolio introduction](HOME.md), corpus/final-answer checkpoints, fixture reference | Report-backed outcomes, stack, author/source links and learning paths |
| [Comparison](https://jfk-ssa.github.io/chess-analytics-lab/comparison.html) | [Classifier summary](CLASSIFIER_COMPARISON.md), frozen reports and cases | Question-level routing and threshold exploration |
| [Architecture](https://jfk-ssa.github.io/chess-analytics-lab/architecture.html) | [Architecture guide](ARCHITECTURE.md), stage descriptions in the builder | Clickable pipeline stages and implementation links |
| [Metrics and data](https://jfk-ssa.github.io/chess-analytics-lab/metrics.html) | [Metrics](METRICS.md), [dictionary](DATA_DICTIONARY.md), versioned contracts | Searchable contracts/schemas and a denominator illustration |
| [Demo](https://jfk-ssa.github.io/chess-analytics-lab/demo.html) | [Demo walkthrough](DEMO.md), synthetic dashboard screenshots | Actual example screens and copyable commands |
| [Transpositions](https://jfk-ssa.github.io/chess-analytics-lab/transpositions.html) | [Analysis guide](TRANSPOSITIONS.md), checked corpus and position reports | Rankings, route balance, coverage/depth/scatter charts, public fianchetto lenses and route comparisons |
| [Opening learning](https://jfk-ssa.github.io/chess-analytics-lab/opening-learning.html) | [Transposition learning](TRANSPOSITION_LEARNING.md) | Illustrative board, lesson design and evaluation proposal |

| [Analyze my games](https://jfk-ssa.github.io/chess-analytics-lab/import-games.html) | [Local PGN guide](GAME_IMPORT.md), [import contract](../contracts/imported_games.json), authored fixtures | Local worker replay, explicit provider/player selection, bounded reference coverage and summary download |

The [original full comparison report](https://jfk-ssa.github.io/chess-analytics-lab/reports/decisions-routing-comparison.html)
is copied byte-for-byte from its tracked report, rather than rewritten. Historical
Jev repetitions remain separate runs. Fresh Decisions questions have no matching
Jev measurement; the explorer explicitly shows **Not measured** for those cells.

## Build and preview locally

From the repository root, install the pinned documentation dependency once:

```sh
uv sync --locked --no-editable --extra docs
uv run --locked --offline --no-editable --extra docs python scripts/build_docs_site.py
uv run --locked --offline --no-editable --extra docs python -m http.server 8767 --bind 127.0.0.1 --directory work/docs-site
```

Open `http://127.0.0.1:8767/`. Stop the local server with Ctrl-C. Once dependencies
are installed, rebuilding requires no network. Keep any other installed extras
in your commands if you also need them; uv synchronizes the selected extras.
For example add `--extra dashboard --extra dbt` to preserve those environments.

```sh
uv run --locked --offline --no-editable --extra docs pytest -q tests/test_docs_site.py
uv run --locked --offline --no-editable --extra docs ruff check scripts/build_docs_site.py tests/test_docs_site.py
```

The builder accepts `--output`, but refuses to replace an existing non-generated
directory. Its default output is ignored under `work/docs-site`; never hand-edit
that HTML. Edit the Markdown, contracts, or `site/assets/site.css` and
`site/assets/site.js`, then rebuild. The optional `docs` extra pins the same
Markdown version already present in the lockfile; the application does not need it.

## Learn from the interactions

On Comparison, start with the 40 shared historical questions to compare rules,
both Jev repetitions and Decisions on the same inputs. Switch to the 24 fresh
questions to inspect Decisions against rules. Moving the threshold only applies
a gate to saved probabilities; it does not rerun a classifier. A stricter gate
usually accepts fewer questions. Inspect both accepted errors and fallbacks.
The frozen policy remains 0.70. Exploring other values on evaluation questions
does not validate a replacement policy. Routing correctness is distinct from
final-answer correctness; the report keeps replay evidence separate from live runs.

On Architecture, follow source bytes through snapshots, marts, metrics, tools and
evaluation. Open each stage to see its responsibility and its actual code.
On Metrics and data, search `clock`, `rating` or `denominator`. The slider starts
with the synthetic demo's 3 proxy errors among 6 evaluable moves and 2 missing
evaluations. Adding hypothetical missing evaluations reduces coverage while the
proxy rate stays 3/6. Missing evaluation is not evidence of a correct move.
On Demo, follow the commands against the tiny authored fixture. Screenshots show
actual local Overview and fixture-replay views; they are illustrations, not
population findings or fresh model responses. To refresh them, run the full
[offline demo](DEMO.md), capture those views and replace only the two named PNGs
in `site/assets`. Never capture personal-provider settings or private games.

On Transpositions, choose Elite or Public, then a recorded opening family or public fianchetto lens.
The default ranking requires multiple move orders; switch to recurring positions
to include frequently repeated boards with one observed route. Select a row to
inspect its board and common routes. Continuations show recorded choices, not
engine recommendations. The statistics use the selected view's game denominator.
Top-set coverage counts a game once across all selected positions. Expand the
family/depth details to inspect the full family inventory and endpoint convergence.
Keyboard users can select rows with Enter/Space and scroll table regions.

## Rebuild opening-position evidence

Ordinary site builds use the tracked compact report and require no corpus files.
Regeneration requires the separate full lab's retained, hash-matching opening
index and PGNs. Install the existing DuckDB/chess dependencies, then run:

```sh
uv run --locked --offline --no-editable python scripts/build_opening_positions.py --corpus-root /path/to/full-lab
uv run --locked --offline --no-editable python scripts/summarize_opening_positions.py --snapshot work/opening-positions/published/SNAPSHOT_ID
```

Use the extraction command's printed snapshot path. Output stays in ignored
`work/opening-positions/`; never put it inside the source corpus. The plan reserves
6 GB of free disk and caps derived storage at 8 GB. Per-source hash-checked shards
support resumption. Summary uses a 1 GB DuckDB memory cap and 2 GB spill cap. After
reviewing a regenerated report, refresh the checkpoint's hashes for the report,
plan, contract and two extraction/aggregation scripts together. The website rejects
source/cohort drift, changed receipt hashes, invalid boards/routes/continuations,
inconsistent frequencies and impossible coverage. It generates SVGs only for the
published bounded rankings; game-level data remain local.

## Publication and acceptance

[The Pages workflow](../.github/workflows/pages.yml) runs on pushes to `main`,
pull requests, or manual dispatch. Pull requests build and check; only `main`
deploys to the `github-pages` environment. Pages uses the GitHub Actions source.
The build installs the locked docs extra, checks the generator and its regression
tests, and uploads only the generated static output. Deployment receives the
minimal Pages/OIDC permissions; no personal-provider secret is supplied.
Existing offline integrity CI remains separate. Public static hosting requires
no cloud database or continuously running application; Actions usage remains
subject to the owner's GitHub plan.

The build checks local link targets and anchors, same-repository GitHub
`blob/main` targets against the checkout, and frozen case/run hashes. External
sites and historical GitHub revisions are outside this offline check. Its
`site-build.json` records source/output hashes, source Git revision, generated
pages and zero live requests. The publication checkpoint records checks and
browser observations in [docs-site-checkpoint.json](../reports/docs-site-checkpoint.json).
Acceptance includes six reachable guide pages, intact full-report bytes, clear
unmeasured cases, working search/threshold/pipeline controls, visible demo
screenshots and usable mobile navigation. Numeric experiments retain their
original dates and evidence; deploying HTML does not create a new benchmark.
Only named public assets and sources enter the build. Ignored datasets, provider
responses, `.env` files, numbered cloud-sync copies and credentials are excluded.

On Opening learning, choose either move order and step backward or forward. After
six half-moves both routes share the same normalized opening position, while
earlier positions diverge. The builder validates the routes with the existing
pinned chess library. This is an illustrative walkthrough, not a trainer or a
measured improvement in learning. The complete rationale is maintained in
Markdown and uses the same visual style and navigation as the other guides.

## Shared appearance

[The visual style guide](DESIGN.md) explains the Inter heading/body font roles,
shared palette, licensing and screenshot refresh process. Fonts are bundled in
both the site and local dashboard; no runtime font-service connection is needed.
Demo images are constrained to 760px and link to their full-size originals.


The corpus selector defaults to the Elite reference cohort (240,086 training
games), with broader public (802,260) and combined views. These counts come from
[the checked corpus report](../reports/opening-corpus.json), not runtime database
queries. The website publishes no account PGNs or full warehouses; its downloadable
PGN example contains authored fixtures. Research sources use
stacked cards; ordinary article tables align to the prose reading width.

## Site review improvements

The eight current pages have distinct descriptions, self-canonical URLs,
Open Graph and Twitter sharing tags, a shared 1200×630 PNG preview and SVG/ICO
favicons. The homepage canonical URL is the directory URL. Sharing metadata is
checked locally; provider preview caches may need to be refreshed after deployment.
The original full report remains a byte-preserved historical artifact.

The homepage promotes counts from the reconciled corpus report and matching
paired-answer checkpoints. These checks establish agreement among retained
artifacts; they do not rerun a live evaluation or rebuild the bulk corpus.
The full question table is collapsed by default and has a wider Question column
inside a keyboard-focusable horizontal scroll region. The frozen report opens
through a link rather than a nested iframe. Mobile navigation scrolls away with
the page. Maintain visible keyboard focus and the approved 78ch reading measure.

The favicon is an original geometric rook; the sharing card is original
typographic artwork. Neither depicts a measured result. They are tracked public
assets and require no runtime image service.


## Local game imports

Serve the build over HTTP; module workers require a secure context (HTTPS or
localhost). Choose UTF-8 Chess.com/Lichess PGNs, select a player per provider, and
analyze selected White games. Try the authored example without an account export.
Imports replace the current session, run in a dedicated worker and use no network
or browser persistence. The import page blocks runtime connections with
`connect-src 'none'`. Clear, cancellation, reload and the 60-second processing
limit terminate the worker. Downloaded summaries remain on the user's device.
The limits are 20 files, 10 MiB, 5,000 framed games, 1,000 plies per game and
32 nested variation levels. Caps reject the session; malformed framing contributes
no partial file. Unsupported completed-game records receive visible dispositions.

The canonical-key and normalization checks compare the browser's pinned chess.js
implementation with independent python-chess replay. Node 24 is used for browser
logic tests in offline CI. No npm install or runtime CDN is needed:

```sh
node --test tests/js/game_import.test.mjs
uv run --locked --offline --no-editable --extra docs pytest -q tests/test_game_import.py tests/test_docs_site.py
node scripts/check_game_import.mjs work/game-import-performance.json
```

The performance script generates at most 5,000 unique-ID authored 20-ply games;
it does not read account files or contact either provider. Its timings are local
fixture evidence, not guarantees for long games, mobile hardware or account history.
See [the verification receipt](../reports/game-import-verification.json).
