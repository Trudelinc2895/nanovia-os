# Cloudflare IaC

This folder provisions the **minimum production baseline** for Nanovia in Cloudflare without hardcoded secrets:

- proxied DNS records for `nanovia.ca`, `www`, and optional `admin`
- a direct `vps` record left unproxied for operational access
- a custom WAF ruleset for common exploit probes
- a baseline rate-limit ruleset for auth/contact/billing POST endpoints

## Required environment variables

```powershell
$env:CLOUDFLARE_API_TOKEN="..."
$env:CLOUDFLARE_ZONE_ID="..."
```

## Usage

```powershell
Set-Location C:\Users\Alienware\nanovia-os\infra\cloudflare
Copy-Item terraform.tfvars.example terraform.tfvars
terraform init
terraform plan
terraform apply
```

## Notes

- Keep `terraform.tfvars` out of git.
- Turnstile widget creation itself remains a dashboard/API step and its **site key / secret key** must be injected through app env only.
- Review the ruleset expressions before apply if your public routes change.

