# 0055. Static documentation publication

- Status: accepted
- Date: 2026-10-09

The owner requested the existing comparison report, a homepage and HTML versions
of comparison, architecture, metrics/data and demo guides. Use GitHub Pages with
a generated static artifact. Keep Markdown and contracts canonical, preserve the
frozen report bytes, and publish only named assets. Add an optional pinned docs
extra instead of a new application dependency. The site interactions use saved
classifications and hypothetical denominator examples; they cannot call providers.
Actual synthetic-demo screenshots illustrate replay, not new model responses.
The metrics prose now explicitly matches the known-opening denominator contract.
A dedicated workflow builds and checks pull requests, and deploys only main.
No live inference, new ingestion or cloud service was provisioned. See SITE.md
and the documentation-site checkpoint for execution and publication evidence.

Publication was verified on `814ffe9`: Pages and offline integrity CI passed;
all public guide/report URLs returned HTTP 200 and the original report bytes
were preserved. Keep deployment evidence separate from model-evaluation claims.
