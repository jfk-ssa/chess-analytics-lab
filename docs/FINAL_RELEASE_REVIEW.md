# Final pre-publication review — 2026-10-05

The four bounded findings below were fixed offline after this review. The
historical findings and the original M8 evidence remain preserved. A fresh
release candidate was committed as `07c1344` and pushed to a private GitHub
repository. GitHub Actions run [37371042615](https://github.com/jfk-ssa/chess-analytics-lab/actions/runs/37371042615)
subsequently passed both jobs on `73b6dfc`; the owner approved public visibility,
and GitHub reports the repository as public.

## Resolution after review

- F1: The runner now writes a durable pending reservation before transport,
  settles it after usage arrives, and reconciles pending records after an
  interruption. A retry can pass previous ignored attempt directories with
  `--prior-attempt`; the runner includes both actual usage and unresolved
  reservations. Mock OpenAI and Jev interruption, pre-transport refusal,
  historical reconciliation, and remaining-cap checks pass.
- F2: The runbook, status and decision record now name the tested Luna
  pairing and distinguish it from the accepted M7 Sol configuration.
- F3: An incomplete run prints its report and exits nonzero; an offline
  quote and a complete run still exit zero. All three CLI paths are tested.
- F4: Rescoring rejects an existing destination or any destination inside
  the original attempt. A subprocess regression confirms the original
  report's bytes remain unchanged.

No additional provider request was made for these fixes. The retained
original M8 attempt and preflight still describe the code/model that ran;
a future live run needs its own fresh preflight and approved caps.

The post-fix local suite passed **108 tests**. A new 523-file clean export
installed from the locked offline cache and passed **95 tests with 13
expected real-data skips**, Ruff, and the complete synthetic demo. Its
wheel and source archive include LICENSE and exclude ignored work, caches,
virtual environments, and private env files; see the
[package inventory](../reports/final-package-inventory.json). The
[post-fix candidate scan](../reports/final-upload-audit.json) found no matching
sensitive content or personal-path patterns. The clean-export check was local
evidence. Hosted CI subsequently passed both
jobs in run 37371042615 on the pushed release; the README is available in the
public repository.

## Findings and bounded fixes

### F1 — Preserve in-flight cost before transport (high priority)

In `src/chess_analytics/jev_e2e.py`, `openai_answer.capture` sets
`transport_started` only in memory and writes its record only after transport
returns. The Jev path has the same ordering. `KeyboardInterrupt` bypasses the
ordinary exception handlers; the outer `finally` restores the key environment
but does not persist the attempt report. A credential-free injected
`KeyboardInterrupt` after transport entry produced **no attempt files and no
report**, losing a $0.001849125 reservation in the synthetic probe. A real
interruption could therefore leave a charged call absent from the cost total
used for a retry. This does not alter the costs of the completed M8 run.

Fix: atomically persist a pending request and its full reservation before
transport; settle it when usage arrives. Persist a stopped summary for
catchable cancellation, and reconcile pending records after process death.
Do not imply that catching Ctrl-C alone handles a hard kill. Retrying must
include unresolved reservations. Test OpenAI and Jev cancellation, a
pre-transport failure, settlement without double counting, and recovery from
an existing pending record. No paid request is needed.

### F2 — State the M8 comparator model explicitly (medium priority)

`jev_e2e.preflight` and `run` call `_resolve_config(None, ...)`, whose default
is `gpt-6-luna`. The tracked actual report confirms Luna in both arms.
`docs/JEV_END_TO_END.md` calls this the M0–M7/product analyst baseline, while
the accepted M7 three-repeat checkpoint used `gpt-6-sol`. The M8 comparison
is fair between its two Luna arms, but it does not measure the effect of
putting Jev in front of the accepted Sol configuration. Model cost affects
whether avoiding six calls can offset 32 Jev calls.

Fix: name Luna in the table and conclusions, distinguish the reusable
checked-tool implementation from the accepted model configuration, and limit
the no-benefit conclusion to this Luna boundary-gate experiment. Keep Jev
unpromoted because a Sol benefit is untested. No rerun or fresh spending is
needed for publication; a Sol comparison can remain optional future work.

### F3 — Return failure when a live attempt stops (medium priority)

`src/chess_analytics/jev_e2e.py:440` prints the result and returns zero even
when `run` has returned `complete: false` with a recorded provider failure.
A shell or automated caller therefore sees success for an incomplete study.

Fix: retain the JSON report but return a nonzero exit code for an incomplete
run. Keep quote/preparation and complete-run success at zero. Verify all
three CLI outcomes with mock responses; no live call is needed.

### F4 — Prevent rescoring over the original attempt (medium priority)

`scripts/replay_jev_e2e.py:55` unconditionally writes `--output`. Passing the
original attempt's `report.json` as that output destroys the original live
report after reading it, despite the command's preservation contract.

Fix: require a fresh destination outside the input attempt directory, with
resolved-path checks, and reject an existing output. Test collisions and a
normal fresh output. Keep the original M8 live and rescore files unchanged.

## Verification completed

- Exported all 520 tracked and non-ignored candidate files into an isolated
  directory, without `.git`, credentials, bulk data, or prior virtualenv.
- Installed the locked dbt/dashboard environment offline from the existing
  dependency cache using a normal wheel installation.
- The export passed **90 tests with 13 expected real-data skips**, Ruff, and
  the complete synthetic demo. The prior unchanged local suite passed 103.
- Local Markdown file links resolve. External links were not revalidated.
- Built the source archive and wheel. Both include LICENSE; archive inventory
  found no ignored `work/`, virtualenv, uv cache, or private env-file payloads.
  The source archive is about 957 KB and the wheel about 100 KB.
- The existing current-candidate/history pattern audit found no matching
  sensitive patterns or personal paths in the candidate and 33 reachable
  commits. This is a bounded pattern scan, not a guarantee of secret absence.
- GPL-3.0-or-later is already selected and declared. No owner license decision
  remains open. The direct chess dependency retains its stated GPL license.

The source candidate still has 19 modified tracked files and 53 untracked
files before this review's documentation. A release commit must include the
intended new license, modules, fixtures, docs, and reports; publishing the
existing HEAD would omit much of the reviewed work. There is no Git remote,
and no hosted CI result is claimed.

## Publication sequence

Steps 1–3 were carried through the private push. At the last check, both
GitHub Actions jobs on `main` were queued while GitHub reported an incident
delaying assignment of hosted runners. Keep step 3 open until the actual
hosted result is available; local checks cannot substitute for it.

1. Fix F1–F4 with offline regressions; preserve frozen evidence and original
   scores. Re-run focused tests, the local suite, and clean-export checks.
2. Review the staged inventory and commit the complete candidate. Keep the
   existing functional public CLI and historical milestone filenames; a
   broad rename would add risk without improving this release.
3. Create the chosen remote repository, push the reviewed commit, and verify
   the existing Linux CI jobs. Confirm the README renders and its demo path
   is discoverable. A private-first repository is a useful staging step.
4. Publicize the portfolio after CI is green. Optional follow-ups include
   the shared Luna coverage miss, an isolated compatible DuckDB/Jev demo,
   and a separately justified Sol comparison. None requires delaying the
   bounded release fixes above.
