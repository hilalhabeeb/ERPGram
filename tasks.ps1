<#
ERPGRAM developer tasks for Windows (PowerShell).
Mirror of the Makefile. Usage:  ./tasks.ps1 <command>
Example:  ./tasks.ps1 up   |   ./tasks.ps1 dev   |   ./tasks.ps1 test
#>
param(
    [Parameter(Position = 0)]
    [string]$Command = "help"
)

$ErrorActionPreference = "Stop"

function Invoke-Web {
    param([string[]]$Args)
    & docker compose run --rm web @Args
}

switch ($Command) {
    "help" {
        Write-Host "ERPGRAM tasks:"
        "install  Build images and install dependencies",
        "up       Start Postgres in the background",
        "down     Stop and remove containers",
        "migrate  Apply database migrations",
        "seed     Load two demo tenants",
        "dev      Run Django + Tailwind watch (http://localhost:8010)",
        "test     Run the test suite",
        "lint     Lint with ruff",
        "fmt      Format with ruff",
        "messages Extract translations (en + ar)",
        "compilemessages  Compile .po to .mo",
        "tailwind Rebuild CSS once" | ForEach-Object { Write-Host "  $_" }
    }
    "install" { & docker compose build }
    "up"      { & docker compose up -d db }
    "down"    { & docker compose down }
    "migrate" { Invoke-Web @("uv", "run", "python", "manage.py", "migrate") }
    "seed"    { Invoke-Web @("uv", "run", "python", "manage.py", "seed") }
    "dev" {
        & docker compose up -d db
        & docker compose run --rm --service-ports web sh -c "tailwindcss -i static/src/input.css -o static/css/app.css --watch & uv run python manage.py runserver 0.0.0.0:8000"
    }
    "test"    { Invoke-Web @("uv", "run", "pytest") }
    "lint"    { Invoke-Web @("uv", "run", "ruff", "check", ".") }
    "fmt"     { Invoke-Web @("uv", "run", "ruff", "format", ".") }
    "messages" { Invoke-Web @("uv", "run", "python", "manage.py", "makemessages", "-l", "ar", "-l", "en", "--ignore=.venv") }
    "compilemessages" { Invoke-Web @("uv", "run", "python", "manage.py", "compilemessages") }
    "tailwind" { Invoke-Web @("tailwindcss", "-i", "static/src/input.css", "-o", "static/css/app.css", "--minify") }
    "shell"   { Invoke-Web @("uv", "run", "python", "manage.py", "shell") }
    default {
        Write-Host "Unknown command: $Command" -ForegroundColor Red
        Write-Host "Run ./tasks.ps1 help for the list."
        exit 1
    }
}
