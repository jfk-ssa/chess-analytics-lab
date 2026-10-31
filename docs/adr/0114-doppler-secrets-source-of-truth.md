# 0114. Doppler as the secrets source of truth

- Status: accepted on merge
- Date: 2026-10-31

## Motivation

Provider keys were maintained separately in GitHub environment secrets and
ignored local key files. Rotation notes were informal, and a planned
1Password integration was never built. Repository secrets could also hide a
missing environment secret ([ADR 0091](0091-manual-live-eval-workflow.md)).

## Decision

Doppler is the source of truth. The owner reports this final layout:

| Workplace | Project | Config | Provider secret names |
|---|---|---|---|
| `personal` | `chess-analytics-lab` | `dev` (Mac) | `CHESSLAB_OPENAI_API_KEY` |
| `personal` | `chess-analytics-lab` | `prd` | `CHESSLAB_OPENAI_API_KEY`, `CHESSLAB_XAI_API_KEY` |

Config `prd` syncs one-way into this repository's GitHub Environment
`live-eval` secrets. Sync mirrors additions, updates, and deletes, applies no
name transforms, and adds `DOPPLER_*` metadata secrets. There are no
repository-level secrets; the ADR 0091 shadowing risk is cleared.

`.github/workflows/live-eval.yml` stays unchanged. It reads the selected
provider's existing environment secret under `environment: live-eval`.
Required review and the main-only restriction stay. Offline CI and the hosted
Streamlit app remain secret-free.

Locally, run `doppler setup` once from the repository root in workplace
`personal`. Root `doppler.yaml` names only the project and default config
`dev`. Run authorized commands with `doppler run -- uv run ...`. Process
environment is the supported key source; Doppler injects it. There is no
Doppler SDK or runtime fetch in the application. `.env.example` documents
names only and is not loaded.

Non-frozen local loaders (`routing_study`, `routing_analyst`,
`decisions_study`, `jev_e2e`) read keys only from the process environment and
no longer accept key-file CLI flags. The frozen eval modules listed in
`live_runner.FROZEN_FILES` (`preflight`, `experiment`, `live_runner`,
`provider`, and the rest of that set) stay byte-identical to the committed
frozen set: they keep a dormant `--env-file` / key-file fallback that loads
only when the named process env var is unset. Env vars therefore take
precedence under `doppler run`. That fallback is not the recommended path and
will be removed at the next intentional frozen-set change (a new eval
version). Historical live-eval receipts and the public dashboard extract are
never rewritten for a secrets-layout change.

`KEY_ENV`, `XAI_KEY_ENV`, `CHESSLAB_OPENAI_API_KEY`,
`CHESSLAB_XAI_API_KEY`, and `TYPESAFE_API_KEY` retain their names.
The optional TypeSafe routing credential is outside the configured provider
layout above; provision it separately in a personal config before an
authorized routing study. Rotation changes only the value and Doppler note.
Dated labels belong in notes, never in environment variable names.

The local Prefect adapter's `PREFECT_API_KEY` refusal stays unchanged.
Personal configuration, a recorded personal-account acknowledgement, and an
explicit run spending cap remain required. This decision authorizes no live
model calls.

## Consequences

Local operators use `doppler run -- uv run ...` (or an explicitly prepared
process environment). Missing-key errors in the non-frozen loaders name the
variable and suggest `doppler run`. Current runbooks point at Doppler, not
`work/.env*`. Historical ADR prose about local key files remains as history.

Frozen eval source hashes, committed live-eval receipts, and
`data/public/dashboard_extract.json` stay untouched by this secrets move.
Rewriting historical receipts is not allowed. The dormant `--env-file`
fallback in frozen modules is temporary compatibility until the next
intentional frozen-set bump.

The layout above is owner-reported configuration, not a credential-backed
audit performed during this edit. No secret values are read and no live
model requests are made to validate this migration. Rollback is disabling
sync and restoring manual environment secrets.

## Rejected alternatives

- 1Password: the integration was never built; Doppler replaces that plan.
- Runtime fetch with a Doppler service token: adds a credential and workflow
  changes where environment sync already supplies the stable names.
- Manual GitHub copies: creates a second place to maintain rotations.
- Dated secret names or repository secrets: breaks the stable name contract
  or restores the ADR 0091 shadowing risk.
- Rewriting committed live-eval receipts to absorb frozen-hash churn from a
  secrets-layout edit: historical receipts are evidence artifacts and stay
  byte-stable.

## References

- [Doppler CLI](https://docs.doppler.com/docs/cli): `doppler.yaml`, setup,
  and process environment injection.
- [GitHub Actions sync](https://docs.doppler.com/docs/github-actions).
- [Sync creation reference](https://docs.doppler.com/reference/syncs-create).
