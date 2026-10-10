# 0037. Pin M7 baseline and isolate M8 variants within one repository

- Status: accepted
- Date: 2026-10-04

Tag accepted M7 commit `f814377` as `m7-baseline`. Keep the checked-tool
core and baseline evaluation runnable without Jev. Add each candidate Jev
decision as an explicit, separately scored mode on frozen inputs, with one
intervention active at a time. Use temporary branches for development as
needed, but do not maintain independent repository forks or duplicate the
data pipeline; that would make drift harder to separate from Jev's effect.
Use the same scorer and log code revision, model/version, thresholds, cost,
latency and fallback. The personal TypeSafe key belongs only in an ignored
named local env file; API login is not proof of entitlement, and no Jev
inference is authorized before a separate frozen M8 cap.
