# EPMS Calendar + Management Hub — Deployment & Validation

## Important

This release adds the Calendar/Management subsystem without deleting existing EPMS records. **Back up the production PostgreSQL database before applying migrations.** Do not run migration tests against the live database.

## 1. Local Windows test

Open PowerShell in the EPMS project folder.

```powershell
python --version
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py test --verbosity=2
```

Then run the supplied validation script:

```powershell
.\scripts\validate_epms.ps1
```

If PowerShell blocks scripts for the current session:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\scripts\validate_epms.ps1
```

## 2. Git safety checkpoint

Before committing:

```powershell
git status
git branch --show-current
git log -5 --oneline
```

Create a feature branch if you want a manual review first:

```powershell
git checkout -b feature/calendar-management-hub
```

## 3. Commit the tested release

```powershell
git add .
git status
git diff --cached --check
git commit -m "Add Calendar and Management Hub"
git push -u origin feature/calendar-management-hub
```

GitHub Actions will run the three validation passes defined in `.github/workflows/epms-calendar-validation.yml`.

Do **not** merge to `main` until the workflow is green.

## 4. Merge to main

After the GitHub Actions checks pass:

```powershell
git checkout main
git pull origin main
git merge --no-ff feature/calendar-management-hub
git push origin main
```

Render will then deploy the `main` branch using the existing `render.yaml` build command. That command already runs `collectstatic` and `migrate` before starting Gunicorn.

## 5. Render verification

After deployment, open Render Logs and confirm:

- build completed successfully
- migrations completed successfully
- Gunicorn started
- no Django system-check errors

Then sign in and test in this order:

1. Employee → Calendar opens.
2. Employee → click a date → leave request opens with the date pre-filled.
3. Submit annual leave → manager receives a new EPMS To-Do.
4. Manager → Management Hub → Approvals.
5. Approve the request → employee calendar shows leave.
6. Repeat and decline without a reason → decline must fail.
7. Decline with a reason → employee can see their own reason.
8. Sign in as another employee → the private decline reason is not visible.
9. Configure recurring WFH days.
10. Submit a WFH swap → manager receives a To-Do.
11. Approve the swap → calendar changes only for the requested occurrence.
12. Create a project deadline involving multiple modalities → calendar shows one deadline with combined scope codes.
13. Assign the milestone to the manager/director → the event is bold/action-required for that person.
14. Verify ordinary employees cannot access `/management/`.
15. Verify managers can access their team scope.
16. Verify directors can use company/team visibility.
17. Verify Company Admin can see all approvals and management information.

## 6. Render migration safety

The normal Render build runs:

```text
pip install -r requirements.txt
python manage.py collectstatic --noinput
python manage.py migrate
...
```

For a production database, take a PostgreSQL backup/snapshot before the first deployment containing the new migrations.

To inspect the migration plan locally:

```powershell
python manage.py migrate --plan
```

## 7. Approval escalation job

The release includes:

```powershell
python manage.py process_calendar_approvals
```

This creates in-app reminder/escalation To-Dos for stale approvals. It is safe to run repeatedly because duplicate open reminders are avoided.

For fully automatic processing, schedule this command as a Render Cron Job later. Email notifications should be added after the in-app workflow is proven; no SMTP/Microsoft credentials are required for this release.

## 8. Rollback

Do not manually delete migrations or database tables.

If a deployment fails:

```powershell
git log --oneline -10
git revert <bad-commit>
git push origin main
```

If a migration has already changed production schema, restore the database backup according to the approved rollback plan before reversing application code. Do not guess at production database rollback commands.
