# 0011. Shorter local key variable

- Status: accepted
- Date: 2026-10-03

Use `CHESSLAB_OPENAI_API_KEY` as the one allowed environment variable for a
personal API key. The user requested removing `PERSONAL` from the variable
name. Personal-account acknowledgement, explicit configuration, and the total
run spending cap remain separate required gates. The former longer variable
is not read as a fallback. No key value was accessed or migrated.
