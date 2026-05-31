# Private Repo Seed

Use `scripts/export_private_repo_seed.ps1` to create a sanitized starter folder for a private Nanovia support repository.

## Included

- reusable infra and VPS hardening scripts
- `.env.example` style templates only
- AI prompts, policies, and schemas
- neutral security and operations docs
- deployment validation helpers

## Excluded

- real `.env` files and local overrides
- API keys, tokens, webhook secrets
- generated Stripe outputs
- databases, logs, caches, and runtime state

## Command

```powershell
cd C:\Users\Alienware\nanovia-os
powershell -ExecutionPolicy Bypass -File .\scripts\export_private_repo_seed.ps1
```

To overwrite the target folder:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\export_private_repo_seed.ps1 -Force
```

Default export target:

`C:\Users\Alienware\Desktop\Nanovia-Private-Repo-Seed`

## Recommended use

1. create a new private GitHub repository
2. copy the exported seed into that repository
3. review templates before first commit
4. store secrets only in vaults, GitHub Secrets, or the VPS `.env`
