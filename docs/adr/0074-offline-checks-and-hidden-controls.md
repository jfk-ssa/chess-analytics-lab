# 0074. Keep offline checks independent of publication artifacts

- Status: accepted
- Date: 2026-10-10

PR #15 removed the generated opening rankings from the branch tip, but its
unconditional byte check made the standard offline test path fail in a fresh
checkout. CI concealed this by downloading the file before the offline suite.
Keep the checkpoint/pin comparison in the default suite. Move the restored-byte
check into the optional documentation suite, whose Pages workflow explicitly
materializes the pinned publication first. Remove the materialization step from
offline integrity CI. Documentation builds still fail closed when publication
bytes are missing or disagree with the checkpoint; tests never download them.

The same review found that formatting removed `!important` from `[hidden]`.
Later responsive `.toolbar` display rules then exposed controls before explorer
initialization or after loading failed. Restore that precedence with a single
documented Biome suppression on the declaration, rather than disabling the rule
across the stylesheet. Menu changes remain separate follow-up work.

Local verification used the pinned non-editable project wheel. With the rankings
absent, the base offline suite passed 137 tests and skipped 17. After restoring
the immutable publication bytes from local Git history and checking their hash,
the suite with the docs extra passed 152 tests and skipped 16. The eight-page
build checked 349 local links with zero live requests. Ruff check/format,
basedpyright, Biome 2.5.15, ten JavaScript fixture tests and the bounded authored
import check passed. Browser inspection of the same hidden-toolbar fixture that
reproduced the review failure confirmed zero rendered height and no visibility
at desktop and mobile widths after the fix. No live model calls or personal-game
imports were used.
