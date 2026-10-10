# Learning lab visual style guide

This is a small shared style guide for the documentation site and local dashboard.
It introduces no frontend framework or runtime font service. Content and evidence
remain the product; typography helps readers distinguish explanations, controls
and measured values.

## Typography and visual roles

| Role | Choice | Reason |
| --- | --- | --- |
| Guide headings | Inter, weight 600 | Matches the body and dashboard with one consistent family |
| Body, navigation, cards, tables | Inter Medium, weight 500; emphasis 600–650 | Clear screen reading and restrained emphasis |
| Dashboard text and headings | Inter Medium body; headings weight 600 | Compact analytical interface without oversized heavy titles |
| Code and technical identifiers | Existing system monospace | Separates execution instructions and identifiers |
| Numbers in tables | Tabular numerals; numeric cells aligned right | Easier comparison across rows |

Guide body text uses Inter Medium (500) at 14px/1.55 with 0.01em tracking.
The page title scales from 28px to 36px; section headings are 23px. Dashboard
body text remains 14px with approximately 32px headings and native Streamlit
spacing. Use size and spacing before extra bold; enlarged text must reflow.

## Layout specification — approved October 9, 2026

One outer canvas establishes the left and right edges of each page. Reading
measure is an inner text limit, not a competing width for bordered components.

| Token / rule | Value | Applies to |
|---|---|---|
| Page width | `--page-width: 1120px` including page padding | Shared main canvas; 1064px usable content at the desktop maximum |
| Reading measure | `--reading-width: 78ch` | Paragraphs, lists, text inside panels and research cards |
| Panel padding | `--panel-padding: 24px`, 18px on narrow screens | Example panels and screenshot frames; other compact components have documented smaller spacing |
| Grid gap | `--grid-gap: 16px` | Card, research and corpus grids |
| Screenshot limit | `--image-width: 760px` | Image inside its full-width figure frame, aligned left |
| Compact contents | Full canvas; 12px vertical / 24px horizontal padding | One border, with contents text limited to 78ch |
| Small disclosures | Full canvas; 14px vertical / 20px horizontal padding | Searchable definition/schema panels |

### Component boundaries

- Contents panels, tables, research-card frames, screenshots and interactive
  panels use the full available outer width. No per-page table-width heuristic.
- Prose stays at 78ch inside that canvas. Headings may extend beyond it. Code
  blocks use the canvas and contained scrolling for long lines.
- Home cards use two equal columns; an unmatched fifth card spans the final row.
  At 750px and below, grids become a single column.
- The denominator example is one panel containing its explanation, slider,
  results and caveat. Related content does not acquire independent outer edges.
- Screenshots retain their 760px image limit inside full-width figure frames.
  Captions and full-size links align with the image. Do not upscale small assets.
- Tables scroll inside their container when their minimum width exceeds the
  viewport. Paragraphs never require horizontal scrolling.
- Keep one contents border; strip the generated Markdown TOC wrapper.

### Table alignment contract

Declare each numeric or currency column by its header/role in the builder or
interactive row renderer. Do not infer alignment from individual cell strings.
Text headers/cells align left. Numeric headers/cells align right with tabular
numerals. An annotation cannot change a column's alignment.

Currency values in the comparison guide display at least nine decimal places,
padding with zeros and preserving greater source precision if present. The
underlying report values remain unchanged. Put `Simulated` below the aligned
amount in smaller muted text. Numeric values stay together; headings may wrap.
Dynamic probability and corpus count/rating columns follow the same contract.

### Visual acceptance examples

| Page / example | Required observation |
|---|---|
| Comparison final-answer table | Numeric headers and all three amounts align right; simulated amount has a separate note |
| Homepage paths / contents / table | Shared outer edges; equal paired cards and full-span final card; no nested contents border |
| Metrics denominator example | Explanation, slider, results and caveat share one full-width panel |
| Opening learning research and corpus | Full-width frames with bounded text; cohort controls and legal board remain usable |
| Demo screenshots | Full-width figure frame, image at most 760px, working full-size link |
| All six pages | Common canvas, readable prose, no page-wide horizontal overflow; narrow-screen content reflows |

Record actual browser observations and viewport sizes in status. Build/link/lint
checks and existing hosted CI are separate from visual acceptance. These rules
apply to current generated guides; the frozen comparison report remains its
original historical artifact.

The shared palette is warm paper `#faf9f5`, dark teal text `#203433`, muted text
`#586c69`, action teal `#116559`, pale panels `#eaf1eb`, borders `#d7ded7` and
an orange text/focus accent `#a84a1f`. Its contrast is 5.44:1 on paper and 4.99:1
on pale panels. The muted text on paper meets normal-text contrast
requirements. Keep textual error labels alongside color; color alone is not a
sufficient explanation. Maintain visible keyboard focus, wrapping navigation,
scrollable tables and reduced-motion support. Spacing uses a 4px base with
larger gaps between sections; cards have subtle borders and restrained corners.

The homepage adds a three-column results grid, stacked at 750px and below.
The header becomes non-sticky at that breakpoint. The opening board fills its
mobile column. Comparison question details stay collapsed until opened, with
a 320px Question column in a contained table. Definition JSON wraps long lines;
executable command blocks keep contained scrolling. The original comparison
report is linked as a separate artifact, preserving its historical appearance.

## Where the styles live

- [Website CSS](../site/assets/site.css) defines typography, colors, components
  and responsive behavior. The `--font-body` and `--font-heading` tokens define
  the font roles.
- [Streamlit configuration](../.streamlit/config.toml) uses supported theme
  settings for the same palette and Inter. Launch from the repository root so
  Streamlit loads this file. Restart the server after font/theme changes.
- [Website builder](../scripts/build_docs_site.py) copies only named assets.
  The site and dashboard share the same checked Inter file from
  `src/chess_analytics/dashboard/static/fonts`. All current guide and dashboard text uses Inter
  except code, which keeps its monospace role.

The font files are Latin-subset normal-style variable WOFF2 files. Other scripts
and unsupported glyphs use the fallback fonts; italic text can use synthesized
italics. Body/heading CSS uses `font-display: swap`, so content remains readable
while fonts load. No fonts are downloaded at runtime from another service.
Pinned Fontsource package versions, original download URLs, file hashes and
licenses are recorded in [font provenance](../site/assets/fonts/provenance.json).
The fonts retain their SIL Open Font License; they are not relicensed under the
project's GPL. See [third-party notices](../THIRD_PARTY_NOTICES.md).

## Images and evidence

Dashboard screenshots are captured from the actual synthetic demo. Display the image inside a full-width figure frame
at no more than 760px wide and provide a full-size image link rather than
stretching small images across the page. Recapture Overview and the
`portfolio-opening` replay after a dashboard appearance change. The screenshots
illustrate authored fixture behavior, not new observations or model responses.
The original frozen comparison report remains unchanged, including its original
styling. New guide styling surrounds that report without rewriting evidence.

## Verify a style change

Build the site using [the website runbook](SITE.md). Check the homepage,
architecture, comparison table and demo guide on desktop and a narrow mobile
viewport. Verify loaded local fonts, heading hierarchy, readable line lengths,
keyboard navigation, working controls and full-size screenshot links. Check the
local dashboard's font and light theme, then recapture images. Run the existing
publication regressions and Ruff; publish only after the visual checks pass.

References: [Fontsource installation](https://fontsource.org/docs/getting-started/install)
and [Streamlit self-hosted fonts](https://docs.streamlit.io/develop/tutorials/configuration-and-theming/static-fonts).
