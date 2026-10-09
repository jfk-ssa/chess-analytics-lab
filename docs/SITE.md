# Documentation website runbook

The public documentation homepage is
[Chess Analytics Lab](https://jfk-ssa.github.io/chess-analytics-lab/).
Markdown stays the maintained source; HTML adds navigation, interactive learning
examples and a browser-rendered version of the existing comparison report.
The site is static: it cannot run the analyst, contact a model or download games.

## What to read and what to maintain

| Published page | Maintained sources | What HTML adds |
| --- | --- | --- |
| [Homepage](https://jfk-ssa.github.io/chess-analytics-lab/) | [Documentation guide](README.md) | Four learning paths and common navigation |
| [Comparison](https://jfk-ssa.github.io/chess-analytics-lab/comparison.html) | [Classifier summary](CLASSIFIER_COMPARISON.md), frozen reports and cases | Question-level routing and threshold exploration |
| [Architecture](https://jfk-ssa.github.io/chess-analytics-lab/architecture.html) | [Architecture guide](ARCHITECTURE.md), stage descriptions in the builder | Clickable pipeline stages and implementation links |
| [Metrics and data](https://jfk-ssa.github.io/chess-analytics-lab/metrics.html) | [Metrics](METRICS.md), [dictionary](DATA_DICTIONARY.md), versioned contracts | Searchable contracts/schemas and a denominator illustration |
| [Demo](https://jfk-ssa.github.io/chess-analytics-lab/demo.html) | [Demo walkthrough](DEMO.md), synthetic dashboard screenshots | Actual example screens and copyable commands |

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

The build checks local link targets and frozen case/run hashes. Its
`site-build.json` records source/output hashes, source Git revision, generated
pages and zero live requests. The publication checkpoint records checks and
browser observations in [docs-site-checkpoint.json](../reports/docs-site-checkpoint.json).
Acceptance includes five reachable pages, intact full-report bytes, clear
unmeasured cases, working search/threshold/pipeline controls, visible demo
screenshots and usable mobile navigation. Numeric experiments retain their
original dates and evidence; deploying HTML does not create a new benchmark.
Only named public assets and sources enter the build. Ignored datasets, provider
responses, `.env` files, numbered cloud-sync copies and credentials are excluded.
