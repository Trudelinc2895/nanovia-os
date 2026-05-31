param(
    [string]$TargetRoot = "$env:USERPROFILE\Desktop\Nanovia-Private-Repo-Seed",
    [switch]$Force
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$repoRoot = Split-Path -Parent $PSScriptRoot
$safePaths = @(
    ".github",
    "docs\AI_ARCHITECTURE.md",
    "docs\TENANT_AI.md",
    "docs\MEMORY_POLICY.md",
    "docs\OPENAI_COST_CONTROL.md",
    "docs\VPS_PERMANENT_LOCK.md",
    "docs\PRIVATE_REPO_SEED.md",
    "docs\SECURITY_CHECKLIST.md",
    "docs\SECURITY_PUBLIC_BOUNDARY.md",
    "docs\NEW_PROJECT_SECURITY_TEMPLATE.md",
    "infra\scripts\lock-vps-forever.sh",
    "infra\scripts\audit-vps-lockdown.sh",
    "infra\scripts\fresh-install.sh",
    "infra\scripts\setup-deploy-user.sh",
    "infra\docker\Caddyfile",
    "infra\docker\Caddyfile.https",
    "infra\docker\Caddyfile.waf",
    "infra\docker\api.Dockerfile",
    "infra\docker\web.Dockerfile",
    "infra\docker\orchestrator.Dockerfile",
    "infra\env\.env.example",
    "infra\env\.env.dev.example",
    "infra\env\.env.staging.example",
    "packages\ai",
    ".env.example",
    ".env.sandbox.example",
    ".gitignore",
    "README.md",
    "SECURITY.md",
    "SECURITY_MASTER.md",
    "scripts\validate_runtime_env.py",
    "scripts\check_health.py",
    "scripts\check_public_entrypoint.py",
    "scripts\deploy_vps.py",
    "scripts\secure_vps.py"
)

$excludePatterns = @(
    "\.env$",
    "\.env\.(?!example$|sandbox\.example$)",
    "\.db$",
    "\.sqlite3?$",
    "\.log$",
    "__pycache__",
    "\.pytest_cache",
    "stripe.*output",
    "sandbox-audit\.jsonl$",
    "terraform\.tfvars$",
    "\.tfstate",
    "secrets?",
    "tokens?"
)

function Test-SafePath {
    param([string]$RelativePath)

    foreach ($pattern in $excludePatterns) {
        if ($RelativePath -match $pattern) {
            return $false
        }
    }
    return $true
}

if ((Test-Path $TargetRoot) -and -not $Force) {
    throw "Target already exists. Use -Force to overwrite: $TargetRoot"
}

if (Test-Path $TargetRoot) {
    Remove-Item -Recurse -Force $TargetRoot
}

New-Item -ItemType Directory -Path $TargetRoot | Out-Null

$manifest = New-Object System.Collections.Generic.List[string]

foreach ($relative in $safePaths) {
    $source = Join-Path $repoRoot $relative
    if (-not (Test-Path $source)) {
        continue
    }

    if (Test-Path $source -PathType Container) {
        Get-ChildItem -Path $source -Recurse -File | ForEach-Object {
            $repoRelative = $_.FullName.Substring($repoRoot.Length + 1)
            if (-not (Test-SafePath $repoRelative)) {
                return
            }

            $destination = Join-Path $TargetRoot $repoRelative
            $destinationDir = Split-Path -Parent $destination
            if (-not (Test-Path $destinationDir)) {
                New-Item -ItemType Directory -Path $destinationDir -Force | Out-Null
            }
            Copy-Item -Path $_.FullName -Destination $destination -Force
            $manifest.Add($repoRelative) | Out-Null
        }
        continue
    }

    if (-not (Test-SafePath $relative)) {
        continue
    }

    $destination = Join-Path $TargetRoot $relative
    $destinationDir = Split-Path -Parent $destination
    if (-not (Test-Path $destinationDir)) {
        New-Item -ItemType Directory -Path $destinationDir -Force | Out-Null
    }
    Copy-Item -Path $source -Destination $destination -Force
    $manifest.Add($relative) | Out-Null
}

$readme = @"
# Nanovia Private Repo Seed

This folder was exported from `nanovia-os` with a conservative allowlist.

Included:
- infrastructure scripts and hardening helpers
- `.env.example` style templates only
- AI prompt, policy, and schema files
- neutral security and operations docs

Excluded on purpose:
- real `.env` files
- API keys, webhook secrets, tokens
- Stripe generated outputs
- databases, logs, caches, and local runtime state

Recommended next steps:
1. Create a new private GitHub repository.
2. Copy this folder into that repository root.
3. Review each template before committing.
4. Fill secrets only in vaults, GitHub Secrets, or the VPS `.env`.
5. Enable branch protection and secret scanning.
"@

$readmePath = Join-Path $TargetRoot "README.private-seed.md"
[System.IO.File]::WriteAllText($readmePath, $readme.Trim() + "`n", [System.Text.UTF8Encoding]::new($false))
$manifestPath = Join-Path $TargetRoot "SEED-MANIFEST.txt"
$sortedManifest = @($manifest | Sort-Object)
[System.IO.File]::WriteAllLines($manifestPath, $sortedManifest, [System.Text.UTF8Encoding]::new($false))

Write-Host "Seed exported to: $TargetRoot"
Write-Host "Files copied: $($manifest.Count)"
