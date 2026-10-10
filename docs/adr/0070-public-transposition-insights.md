# 0070. Separate public transposition analysis from learning design

- Status: accepted
- Date: 2026-10-10

The owner requested two reviewed, unmerged PRs: public page separation and richer
position analysis first, then local file import and a personal reference overlay.
Username/API acquisition is dropped from this delivery. PR #11 remains an open
baseline, so the first new PR targets its branch and the second targets the first.

Preserve /transpositions.html and its position-explorer anchor. Move the research,
illustrative board and evaluation proposal to /opening-learning.html, preserving
useful old fragments as learning-guide links. Metrics & data registers the opening
contract and derives its definition count. All pages keep distinct metadata,
canonicals, favicon and sharing assets; a sitemap lists the generated pages.

Extend the checked report to version 1.1.0 without changing the source visits,
cohort eligibility or existing published figures. Add complete known family/ECO
breadth, route balance with an acyclic-game denominator, route remainders, and
union coverage at every N=1..20. Charts have text/table alternatives. The scatter
is limited to ranked boards; depth compression compares all openings, independent
of family/lens filters. No learning-effect or engine-quality claim follows.

Three public fianchetto facets use played UCI moves by ply 20, require first White
move d4, and have matching-game denominators. Their move-sequence rules are
versioned independently of recorded opening labels. Include boards before and
after g3 and expose how many arrivals have already played g3. These facets are not
exhaustive opening taxonomy and contain no personal account history.

The initial independent ranking check exceeded its 2GB scratch cap. Bound expensive
route grouping to boards that could displace a published frequency rank, use one
thread and preserve the cap. The rerun reconciles 64 rankings, 1,280 curve points
and 668 details against raw checked visits. Retain that failed attempt in the
publication receipt. Local fixture/offline tests and browser checks remain
separate from hosted CI, deployment, screen-reader or physical-device validation.
