# 0047. Publication fixes after review

- Status: accepted
- Date: 2026-10-05

Resolve the four findings with no new model calls. Persist a pending cost
reservation before each provider transport, reconcile pending/settled
records after an interrupt, and accept previous attempt directories when
enforcing a cumulative cap on retry. A pending record may conservatively
reserve a call that never reached the provider; that is safer than treating
unknown usage as free. Return nonzero for incomplete runs. Require a fresh
rescore destination outside the original attempt. Name the Luna pairing in
M8's conclusion and leave Sol integration unclaimed. Preserve frozen run
reports, hashes and raw attempts; any future live run must re-preflight
under a newly approved cap.
