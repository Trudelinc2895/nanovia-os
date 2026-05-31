# OpenAI Cost Control

Nanovia AI usage is metered on every request.

Current defaults:

* minimum markup: `x3`
* ideal markup range: `x4` to `x6`
* credit value: `0.01 USD`

Tenant usage is debited through the existing sandbox credit ledger before the AI response is accepted.
