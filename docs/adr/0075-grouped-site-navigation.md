# 0075. Group site navigation and collapse it on mobile

- Status: accepted
- Date: 2026-10-10

The eight-link header had grown into a long, wrapping row. Use four entries:
Home, Openings, Analyze my games, and The lab. Keep Opening learning before
Transpositions inside Openings. Put Run the demo, Metrics & data, AI comparison,
and Architecture inside The lab. Local PGN analysis remains directly visible.
Retain all page URLs, the shared header, and one current-page marker per page;
highlight the containing group when its current link is collapsed.

Use native details/summary groups, with click and keyboard activation rather
than a hover dependency. At 960 CSS pixels and below, enhance the navigation
with a collapsed Menu button and an in-flow list. JavaScript dismisses groups
on outside clicks, focus departure, Escape, and link selection; Escape restores
focus to the disclosure or Menu. Resizing restores focus when its prior control
becomes hidden. Without JavaScript, the full navigation stays visible and native
disclosures remain usable. Use ordinary navigation links rather than application
menu roles. Keep the scoped `[hidden]` precedence from ADR 0074.

Generated-page regression checks verify all eight destinations, the opening
order, the current-page link, and the toggle's controlled navigation ID on every
page. Local browser checks covered Enter/Space/Tab/Escape, one open group,
outside-click dismissal, mobile page navigation, both resize focus paths,
current-group highlighting, the import page's CSP, and native fallback without
scripts. The opening-learning page fit at 320 CSS pixels without horizontal
overflow. Static generation checked 349 local links across eight pages with
zero live requests. The documentation suite passed 15 tests; Ruff check/format,
basedpyright, and Biome 2.5.15 passed. These are local UI and authored fixture
checks, not screen-reader certification or measured learning outcomes.
