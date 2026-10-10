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
with a collapsed Menu button and an in-flow list. A same-origin blocking script
adds `js` to `html` before first paint. Under that class, CSS hides the link
list while Menu's `aria-expanded` is false and shows the button. The toggle does
not use the `hidden` attribute, so `[hidden]`'s `!important` rule does not keep
Menu undisplayed after the class is set. JavaScript dismisses groups on outside
clicks, focus departure, Escape, and link selection; Escape restores focus to
the disclosure or Menu. Resizing restores focus when its prior control becomes
hidden. Without JavaScript, the class is absent, Menu stays undisplayed, the
full navigation stays visible, and native disclosures remain usable. Use
ordinary navigation links rather than application menu roles. Keep the scoped
`[hidden]` precedence from ADR 0074 for controls that still use that attribute.

Generated-page regression checks verify all eight destinations, the opening
order, the current-page link, and the toggle's controlled navigation ID on every
page. Local browser checks covered Enter/Space/Tab/Escape, one open group,
outside-click dismissal, mobile page navigation, both resize focus paths,
current-group highlighting, the import page's CSP, and native fallback without
scripts. The opening-learning page fit at 320 CSS pixels without horizontal
overflow. Static generation for the compact-paint change checked 357 local
links across eight pages with zero live requests. A local check at 390×844,
with CPU slowed 4× and the network at 400 ms / 400 kbps, found the compact Menu
already in the first frame on the homepage and transpositions page.
Navigation-attributed layout shift was 0 on both; the homepage's remaining
shift was 0.00016 from a one-pixel text move, and transpositions retained a
0.020 position-explorer shift. The documentation suite passed 16 tests,
including a check that the header `max-width` in `site.css` and the
`matchMedia` query in `site.js` are the same value. Ruff check/format and
Biome 2.5.15 passed for this change. These are local UI and
authored fixture checks, not screen-reader certification or measured learning
outcomes.
