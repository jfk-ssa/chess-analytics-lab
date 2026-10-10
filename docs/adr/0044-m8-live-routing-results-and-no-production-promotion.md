# 0044. M8 live routing results and no production promotion

- Status: accepted
- Date: 2026-10-05

The owner approved separate cumulative gross caps of $0.05 for two frozen
TypeSafe passes and $0.10 for one structured-analyst comparison. The explicit
personal TypeSafe key authenticated; its model-list endpoint showed aliases,
but the pinned `jev-1.13.0` completed both 40-case passes. Actual scores were
39/40 and 37/40; two routes changed between identical passes. Their total
gross cost was $0.002000376. The existing structured analyst completed a
40-case pass at 33/40 and $0.00226205. It also had a stopped 20-completed-case
attempt at $0.00191639 after `compare_clock_buckets` subtracted null evaluation
coverage. Fix only that null arithmetic, retain its failure and charge, and
verify the regression offline before the complete pass. An earlier preflight
dataset-ID mismatch prevented transport and incurred no charge. OpenAI's M8
cumulative accounted gross was $0.00417844, below its separate cap.

These results compare semantic routes on authored, not independently
human-adjudicated labels. The structured analyst executed checked tools over
the small synthetic demo, while Jev received a compact catalog. The
coverage/error and cost table can support learning, but does not establish
end-to-end numerical answer quality or a production improvement. Its
Jev-plus-analyst fallback table is a post hoc replay using observed per-case
costs, not an executed combined system. Keep Jev isolated and the M7 baseline
available until fresh independent references and an end-to-end evaluation
show a practical benefit. DuckDB Jev remains an isolated extension exercise.
