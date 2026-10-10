# 0012. Optional M6 provider JSON

- Status: accepted
- Date: 2026-10-03

For the first M6 pilot, allow `--max-run-usd` instead of a separate personal
provider JSON. This deliberately invokes the same personal-key gate using the
GPT-6 Luna model and Standard text prices verified in official documentation
on 2026-10-03. A future run must reverify current terms. The cap stays
mandatory: an account credit balance is not a run budget, and gross API cost
is recorded even if credit covers it. The live command can load only the named
key from `work/.env` without sourcing other variables or shell code. Keep
`--config` for later model/pricing overrides. No request has occurred yet.
