# 0118. Portfolio presentation from maintained Markdown

- Status: accepted
- Date: 2026-11-01

## Decision

Keep root `PORTFOLIO.md` as the portfolio's only narrative source. After the
existing Markdown conversion and repository-link resolution, `portfolio_page`
adds an intro strip, live-link pills, equal-width topic cards, wrapping source
chips, and quiet Next callouts. The first sentence leads the introduction;
the rest of the paragraph, including the author credit, stays below it. The
shell retains the page title. Decisions and local commands span the canvas.

Render the source Mermaid nodes and upstream edges as a static stage list,
with numbered nodes and linked incoming stages. This preserves the branch
relationships instead of replacing them with a hardcoded sequential pipeline.
No Mermaid runtime or external JavaScript is needed. The supported source
syntax is named bracketed nodes and arrow chains, as maintained in the source.

Reuse the site's Inter, paper, teal, spacing and border tokens. Portfolio prose
has a 70ch reading limit; the card grid uses the full shared canvas. At 750px
the cards stack; at 480px the architecture becomes a vertical list. Source
chips and local command blocks wrap. The shell adds `body.page-portfolio`;
dark preference overrides its palette and shared header colors only. Other
pages retain their existing appearance.

## Verification and limits

The locked offline documentation suite passes 24 tests, including the ten-page
publication and navigation checks, root-source/link checks, architecture
connections, live pills, source chips, author credit and absence of Mermaid
CDN/runtime code. Ruff check and Python formatting checks pass. No package
source changed, so a project-wheel reinstall is unnecessary.

The static build succeeds with zero live requests. Headless Chrome review
at 1280px and 390px in light and dark recorded scrollWidth equal to the
viewport (no horizontal overflow). Desktop uses a 4-up architecture grid and
equal 2-column topic cards; mobile uses a single-column timeline with 48px
live-link pills and 44px Lab destinations. Screenshots:
`/workspace/portfolio-drafts/pr2-{1280,390}-{light,dark}.png`. Nothing is
merged by this change.
