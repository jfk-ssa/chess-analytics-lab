# 0052. Lead the comparison with results

- Status: accepted
- Date: 2026-10-07

The owner requested an upfront results section in the Decisions comparison.
Render a checkpoint-backed summary before the detailed tables, highlighting
routing accuracy, frozen gate behavior, gross spend, retained-answer replay and
the recommendation to keep Decisions optional. Require matching report hashes
when rendering the checkpoint summary. Preserve classifier runs and avoid new
paid calls for this presentation change.

Clarify “baseline” in the report: rules are the simple routing baseline; the
existing Luna analyst is the final-answer baseline. Show baseline, Jev and
Decisions side by side on shared historical cases, separating actual paired
results from Decisions retained-answer replay. Mark Jev/analyst fresh results
as not measured rather than comparing different case sets.
