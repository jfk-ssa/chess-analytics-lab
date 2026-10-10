# 0066. One M7 campaign command

- Status: accepted
- Date: 2026-10-10

The per-month pin, workspace, reference, case, and gate scripts differed by
source pin, opening families, question wording, and checkpoint accounting.
Those differences now live in `config/m7_campaigns.json`. `chesslab m7` runs
`pin`, `workspace`, `reference`, `cases`, and `check` for a campaign id.
New preflights hash that config and `src/chess_analytics/m7_campaign.py`.
Published preflight files keep their original script hashes. A prefix hash
mismatch raises instead of rewriting a per-month JSON. Question text matches
every frozen case file. Shared checkpoint, clock-dev, and repetition scripts stay.
