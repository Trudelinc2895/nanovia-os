$ErrorActionPreference = "Stop"

$root = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$envFile = Join-Path $root ".env.sandbox"
$productsFile = Join-Path $PSScriptRoot "products.json"
$pricesFile = Join-Path $PSScriptRoot "prices.json"
$outputFile = Join-Path $PSScriptRoot "stripe-output.sandbox.json"

if (-not (Test-Path $envFile)) {
    Write-Error ".env.sandbox is missing. Copy .env.sandbox.example to .env.sandbox first."
}

Get-Content $envFile | ForEach-Object {
    if ($_ -match '^\s*#' -or $_ -match '^\s*$') {
        return
    }

    $parts = $_ -split '=', 2
    if ($parts.Count -eq 2) {
        [System.Environment]::SetEnvironmentVariable($parts[0], $parts[1])
    }
}

if (-not $env:STRIPE_SECRET_KEY) {
    Write-Error "STRIPE_SECRET_KEY is required in .env.sandbox."
}

if ($env:STRIPE_SECRET_KEY -like "sk_live_*") {
    Write-Error "Live Stripe keys are forbidden in sandbox."
}

Write-Host "Nanovia Stripe sandbox is prepared in test mode only."
Write-Host "Products definition: $productsFile"
Write-Host "Prices definition:   $pricesFile"
Write-Host "Running bootstrap..."
python "$root\stripe\setup_stripe.py"
if ($LASTEXITCODE -ne 0) {
    Write-Error "Stripe sandbox bootstrap failed."
}
Write-Host "Stripe sandbox output: $outputFile"
