# 0103. Security pins for Pillow and certifi

- Status: accepted on merge
- Date: 2026-10-22

## Motivation

An OSV query of the 204 locked packages found advisories on two of them.
Pillow 11.3.0, pulled in by Streamlit, had 45 GHSA records. OSV marks 3
of those critical, 28 high, and 14 moderate. Pillow 13.0.0 is the
release that closes that set. Streamlit 1.65.0 requires `pillow<13`, so
the dashboard extra cannot install the fix without a newer Streamlit.
Streamlit 1.66.1 accepts `pillow<14,>=9.2.0`. Certifi 2026.7.22 had
GHSA-6q48-6c7w-9gw2, the compromised emSign intermediates, fixed in
2026.10.19. No other locked package had an OSV record.

## Decision

The dashboard extra pins Streamlit 1.66.1, Pillow 13.0.0, and certifi
2026.10.19. `hosted/requirements.txt` pins the same Pillow and certifi
versions, plus the Streamlit pin, so Community Cloud pip cannot resolve
an older release. The other locked versions stay where the new
Streamlit metadata still accepts them. Pandas 2.3.3, protobuf 6.33.6,
Altair 5.5.0, and PyArrow 25.0.1 stay. Streamlit 1.66.1 accepts
`pandas<4,>=1.5.3`, `protobuf<8,>=5.26.1`, and
`pyarrow!=25.0.0,<27,>=10.0.1`.

The hosted page and the local dashboard do not call an API that 1.66
removed. The 1.66.0 notes add widget behavior and fix stretch-chart
height and side-by-side alignment. They do not remove `st.altair_chart`
width, `theme`, `alt`, or `on_select`, `st.table` height, `st.html`, or
`st.cache_data`. [ADR 0094](0094-hosted-read-only-dashboard.md) keeps
1.65.0 as the pin it recorded.

## Consequences

`uv sync` and Community Cloud both install Pillow 13.0.0 and certifi
2026.10.19. A later Streamlit pin has to keep allowing `pillow>=13`.
The certifi pin stays at or above 2026.10.19. Re-query OSV after the
lock changes. This record does not authorize a live model call.
