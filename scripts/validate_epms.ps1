$ErrorActionPreference = 'Stop'

Write-Host "EPMS validation - Pass 1: application checks" -ForegroundColor Cyan
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py test --verbosity=2

Write-Host "EPMS validation - Pass 2: fresh migration" -ForegroundColor Cyan
if (Test-Path .\db.sqlite3) { Remove-Item .\db.sqlite3 -Force }
python manage.py migrate --noinput
python manage.py check
python manage.py test calendar_app --verbosity=2

Write-Host "EPMS validation - Pass 3: upgrade migration" -ForegroundColor Cyan
# Run this pass against a copy of the current production database, never the live database.
Write-Host "For the production upgrade simulation, restore a backup to a separate test database and run:" -ForegroundColor Yellow
Write-Host "  python manage.py migrate --plan"
Write-Host "  python manage.py migrate --noinput"
Write-Host "  python manage.py check"
Write-Host "  python manage.py test calendar_app --verbosity=2"

Write-Host "Static validation complete. Do not deploy until all three passes are green." -ForegroundColor Green
