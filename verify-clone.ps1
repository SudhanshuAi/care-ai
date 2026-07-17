[CmdletBinding()]
param(
    [switch]$SkipBuild,
    [switch]$SkipTests
)

$ErrorActionPreference = "Stop"

function Invoke-Checked {
    param([string[]]$Arguments)

    & docker @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "docker $($Arguments -join ' ') failed with exit code $LASTEXITCODE."
    }
}

if (Test-Path "docker-compose.override.yml") {
    throw "Refusing to run with docker-compose.override.yml present. Remove or rename local overrides so this verification uses only tracked configuration."
}

if (-not (Test-Path ".env")) {
    Copy-Item ".env.example" ".env"
    Write-Host "Created .env from .env.example."
}

$databaseUrl = (
    Get-Content ".env" |
    Where-Object { $_ -match '^\s*DATABASE_URL=' } |
    Select-Object -First 1
)
if ($databaseUrl -notmatch '@db(:|/)') {
    throw "Refusing to run: .env must use the local Docker database host 'db'. Do not run clone verification against a shared or production database."
}

if (-not $SkipBuild) {
    Invoke-Checked -Arguments @("compose", "up", "--build", "-d")
} else {
    Invoke-Checked -Arguments @("compose", "up", "-d")
}

$deadline = (Get-Date).AddSeconds(60)
do {
    try {
        $health = Invoke-RestMethod -Uri "http://localhost:8000/health/ready" -TimeoutSec 5
        if ($health.status -eq "ok" -and $health.database -eq "connected") {
            break
        }
    } catch {
        Start-Sleep -Seconds 2
    }
} while ((Get-Date) -lt $deadline)

if (-not $health -or $health.status -ne "ok") {
    throw "Backend did not become ready within 60 seconds. Run 'docker compose logs backend' for details."
}

Invoke-Checked -Arguments @("compose", "exec", "backend", "python", "-m", "scripts.seed_clinic")

if (-not $SkipTests) {
    Invoke-Checked -Arguments @(
        "compose", "exec", "backend", "ruff", "check", "app", "scripts", "tests", "evaluation"
    )
    Invoke-Checked -Arguments @("compose", "exec", "backend", "pytest", "-q")
}

Write-Host "Clone verification passed. API docs: http://localhost:8000/docs"
