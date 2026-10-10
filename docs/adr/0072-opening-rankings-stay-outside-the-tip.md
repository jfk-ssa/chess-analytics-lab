# 0072. Keep opening rankings reproducible without tracking the generated file

- Status: accepted
- Date: 2026-10-10

`reports/opening-positions.json` is a 1.48 MB generated ranking file. The visit
shards and PGN corpus that produce it stay out of Git, so CI cannot regenerate
it without downloading games. Leave the bytes in Git history at
`c1e3040a3c9542626a3b8cb78e1e7475ea8bcdab` and stop tracking the file at the tip.

CI and the Pages build restore it with `scripts/materialize_opening_positions.py`,
which downloads that immutable blob and checks SHA-256
`31a395044203532224cbb387475ef0bb790c8e88faac98bc9b2a12f5d500c46e` from the
publication checkpoint. A local visit snapshot can still be summarized with
`scripts/summarize_opening_positions.py`. Tests read the restored file and do
not download it. The site continues to publish `assets/opening-positions.json`.
