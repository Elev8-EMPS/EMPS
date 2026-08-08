# Release Test Status — Calendar + Management Hub

## Static release gates completed

- Python AST syntax validation: PASS (3 runs)
- `python -m compileall`: PASS (3 runs)
- `git diff --check`: PASS (3 runs)
- Migration dependency graph validation: PASS (no missing dependencies, no cycles; 3 runs)
- Django template block structure validation: PASS (3 runs)
- Required release-file validation: PASS (3 runs)

## Runtime test limitation in this environment

The repository pins Django 6.0.7. The execution environment used to prepare this package does not have Django installed, and its package index cannot retrieve Django 6.0.7. Therefore a real `manage.py check`, migration execution, Django test suite, browser smoke test, or PostgreSQL upgrade simulation could not honestly be marked PASS here.

The release therefore includes `.github/workflows/epms-calendar-validation.yml`, which performs three runtime validation passes automatically when pushed to GitHub:

1. Full Django application tests and migration consistency.
2. Fresh database migration and Calendar tests.
3. Upgrade migration from the previous Git commit followed by Calendar tests.

**Do not deploy this candidate to production until those GitHub Actions checks are green and the manual Render smoke test in `CALENDAR_DEPLOYMENT.md` has been completed.**
