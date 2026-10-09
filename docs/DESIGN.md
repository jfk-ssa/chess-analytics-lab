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

Guide body text uses Medium (500) at 14px with 1.55 line height, 0.01em letter spacing and prose
limited to roughly 70 characters per line. The page title scales from 28px to
36px; section headings are 23px. Navigation and tables use the same family.
Dashboard body text is 14px and the main title approximately 32px, using
Streamlit's native spacing. Use size and spacing before extra bold. Browser
zoom remains available; avoid fixed-height prose that clips enlarged text.

The shared palette is warm paper `#faf9f5`, dark teal text `#203433`, muted text
`#586c69`, action teal `#116559`, pale panels `#eaf1eb`, borders `#d7ded7` and
an orange accent `#cf612f`. The muted text on paper meets normal-text contrast
requirements. Keep textual error labels alongside color; color alone is not a
sufficient explanation. Maintain visible keyboard focus, wrapping navigation,
scrollable tables and reduced-motion support. Spacing uses a 4px base with
larger gaps between sections; cards have subtle borders and restrained corners.

## Where the styles live

- [Website CSS](../site/assets/site.css) defines typography, colors, components
  and responsive behavior. The `--font-body` and `--font-heading` tokens define
  the font roles.
- [Streamlit configuration](../.streamlit/config.toml) uses supported theme
  settings for the same palette and Inter. Launch from the repository root so
  Streamlit loads this file. Restart the server after font/theme changes.
- [Website builder](../scripts/build_docs_site.py) copies only named assets.
  The site and dashboard share the same checked Inter file from
  `analytics_m4/static/fonts`. All current guide and dashboard text uses Inter
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

Dashboard screenshots are captured from the actual synthetic demo. Display them
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
