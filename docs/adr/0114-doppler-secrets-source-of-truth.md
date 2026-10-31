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
`dev`. Run authorized commands with `doppler run -- uv run ...`.
Application code reads keys only from the process environment; remove the
`work/.env*` loaders and their CLI arguments. There is no Doppler SDK or
runtime fetch in the application. `.env.example` documents names only and
is not loaded.

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

Local operators use Doppler injection or an explicitly prepared process
environment. Missing-key errors name the variable and suggest `doppler run`.
Current runbooks and fixture tests follow that contract. Historical ADR prose
about local key files remains as history. Frozen preflights that bind changed
source hashes must be regenerated before a newly authorized run; retained
failures, replay results, and live receipts are not rewritten.

The layout above is owner-reported configuration, not a credential-backed
audit performed during this edit. No secret values are read and no live
model requests are made to validate this migration. Rollback is disabling
sync and restoring manual environment secrets; restoring local file loading
would require reverting the corresponding code changes.


## Rejected alternatives

- 1Password: the integration was never built; Doppler replaces that plan.
- Runtime fetch with a Doppler service token: adds a credential and workflow
  changes where environment sync already supplies the stable names.
- Manual GitHub copies: creates a second place to maintain rotations.
- Dated secret names or repository secrets: breaks the stable name contract
  or restores the ADR 0091 shadowing risk.

## References

- [Doppler CLI](https://docs.doppler.com/docs/cli): `doppler.yaml`, setup,
  and process environment injection.
- [GitHub Actions sync](https://docs.doppler.com/docs/github-actions).
- [Sync creation reference](https://docs.doppler.com/reference/syncs-create).
