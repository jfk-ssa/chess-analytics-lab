# 0109. Pre-render the opening board

- Status: accepted on merge
- Date: 2026-10-26

## Motivation

CodeQL alert #3 (`js/xss-through-dom`, "DOM text reinterpreted as HTML")
points at `site/assets/site.js`, where the opening widget assigned
`state.svg` with `innerHTML`. That string was parsed from `#opening-data`,
JSON the site builder writes from two fixed, legally replayed lines. The
practical risk is low. The sink still reinterprets text that lived in the
DOM as HTML, which is the bug the query reports.

Parsing the same string with `DOMParser` and `image/svg+xml` would keep a
runtime path from DOM text to inserted markup. The query is about that
pattern. Pre-rendering removes it.

## Decision

The builder writes all 14 boards (2 routes, plies 0–6) into the opening
widget. The shared final position of the first route stays visible. The
other frames use the `hidden` attribute. `site.js` only toggles `hidden`,
then updates the same text labels, aria-label, and button state as before.
The JSON payload no longer includes SVG.

python-chess repeats piece ids such as `white-pawn` and points `<use>` at
them. A visible board would otherwise bind those references to the first
board in the document, including one hidden with `display: none`, and the
pieces would not paint. Each frame gets its own id prefix.

## Evidence

`opening-learning.html` was 556,458 bytes and is 494,792 bytes (−61,666).
Gzipped size went from 81,818 bytes to 27,093 (−54,725). The old page kept
one raw board plus fourteen JSON-escaped copies.

Headless Chrome at 1280×900 (board 420px) and 390px wide (board 316px)
matched the previous pixels on the initial frame. Previous, the route
select, and Home on the range produced the same status, accessible name,
and pixels as the `innerHTML` page, including a board that had been hidden.
No live model call and no credential read.
