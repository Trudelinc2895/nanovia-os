# Memory Policy

Nanovia separates memory by scope:

* `master` for owner-only private notes
* `tenant` for isolated per-tenant memory
* `shared_learning` for anonymized insights only

Secrets are rejected from memory saves and shared learning content is anonymized before persistence.
