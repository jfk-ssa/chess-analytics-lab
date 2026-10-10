# 0076. Show primary guides and a Lab strip

- Status: accepted
- Date: 2026-10-10
- Supersedes: [0075](0075-grouped-site-navigation.md)

The grouped header hid Openings and The lab behind disclosures, and hid every
link behind Menu on small screens. Keep the eight page URLs, and show the work
directly. Primary links are Home, Data pipeline, Transpositions, Analyze games,
and AI analyst. The Lab strip lists Metrics & data, Architecture, Run the demo,
AI comparison, and Opening learning. Data pipeline and Architecture share the
architecture guide. AI analyst and AI comparison share the comparison guide.
The import label is Analyze games so it fits one tablet column. Every link to
the current page carries `aria-current="page"`.

Above 960 CSS pixels the header is sticky. From 601px through 960px it is
static and both groups are five-column grids. At 600px and below it is static:
primary links are full-width 44px rows, and Lab is a wrapping line of text
links at least 24px tall. There is no Menu button, no disclosure, and no
navigation `matchMedia` query, so the early `js` class script is gone.
`site.js` still enhances copy buttons, tables, and the learning controls.

The homepage adds four fully linked preview cards under the hero. Training
games come from `reports/opening-corpus.json`. Elite transposing positions and
the ply-6-to-20 compression sparkline come from the restored
`reports/opening-positions.json` (`cohorts.elite_reference`); the chart uses a
fixed 0–0.50 axis and fails if a point leaves that axis. The 39/40 figure is
the Decisions historical test routing score, reconciled between
`reports/decisions-checkpoint.json` and `reports/decisions-historical-test.json`,
and the card says it is route choice. Analyze games is a PGN teaser with no
number. The position publication is still restored in CI rather than stored on
the branch tip. A missing or hash-mismatched file fails the build with the
existing restoration error.

Generated-page checks cover all eight destinations, duplicate current-page
markers where two labels share a URL, and the CSS that keeps 390, 768, and
1280 from growing a horizontal scroller. A local browser check at those widths
found scroll width equal to the viewport. Header heights were 298.69px at 390
(static), 200.64px at 768 (static), and 109.83px at 1280 (sticky). At 390×844,
with CPU slowed 4× and the network at 400 ms / 400 kbps, the homepage's layout
shift was 0.000028 from a Lab link whose top and height did not change.
Transpositions shifted 0.00483 from the position explorer, not the header.
The header was already at its final height in that frame. Static generation
checked 449 local links across eight pages with zero live requests. The
documentation suite passed 17 tests. The locked offline suite passed 154 tests
and skipped 16. Ruff check/format, basedpyright, and Biome 2.5.15 passed.
These are local UI and authored fixture checks, not screen-reader certification
or measured learning outcomes.
