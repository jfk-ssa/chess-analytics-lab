# Tiny synthetic fixture, version 1

These 26 short PGNs are fabricated test records, not real player behavior.
All names are fixture aliases. Result tags represent adjudicated short games;
they do not imply the board is checkmate. No population analysis uses this file.

The independently specified tally is visible directly in `tiny.pgn`:

| Game suffix | Result/disposition | Eligible count | Draws |
|---|---|---:|---:|
| 0001–0010 | White win | 10 | 0 |
| 0011–0016 | Black win | 6 | 0 |
| 0017–0020 | Draw | 4 | 4 |
| 0021 | Unknown result; retained, excluded from metric | 0 | 0 |
| 0022 | Marked bot; retained, excluded from metric | 0 | 0 |
| 0023 | Casual; excluded | 0 | 0 |
| 0024 | Chess960; excluded | 0 | 0 |
| 0025 | Malformed required Site; quarantine | 0 | 0 |
| 0026 | Illegal Bh6; quarantine | 0 | 0 |

Thus **4 / 20 = 0.20**, with 22 normalized games and 44 participant rows.
One missing rating stays null. All UTC times are absent: dates must not become
invented midnight timestamps. Record 1 contains a clock, record 2 a mate annotation;
M1 preserves the source but does not materialize or interpret these move features.
Duplicate/conflict/truncation scenarios are derived in tests and remain synthetic.
