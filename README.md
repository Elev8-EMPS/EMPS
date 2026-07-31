# EPMS - Stage 2 Django project

Enterprise Project Management System, production platform, built from
the EPMS blueprint (v1.0). This is the initial skeleton: project setup,
tenant-aware data model, and admin screens for CRM, Delivery, and
Finance. No custom UI yet - Django admin is your working screens for now.

## Project structure

```
epms/            Project settings, URLs, WSGI entry point
tenants/         Tenant model + TenantModel base class every other app inherits from
crm/             Organisation, Contact, Enquiry, Proposal
delivery/        Project, Milestone, Task, Document
finance/         Invoice, Payment
```

Every business table has a `tenant` field from day one, even though
only one tenant exists right now - this is what avoids a rewrite if
you expand to more companies later.

## Run it locally

```bash
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

Visit `http://127.0.0.1:8000/admin/` and log in with the superuser you
just created. Before you can add Organisations, Projects, etc., create
one `Tenant` row first (Admin -> Tenants -> Add) - every other record
depends on it.

## Deploy to Render (free)

1. Push this project to a GitHub repository.
2. Go to render.com, sign up (no card needed), and click
   **New -> Blueprint**.
3. Connect your GitHub repo. Render reads `render.yaml` in this
   project and automatically creates the web service *and* the free
   Postgres database together, wired to each other.
4. Click **Apply**. Render builds, runs migrations, and deploys.
5. Once it's live, open the Shell tab on the web service and run:
   ```bash
   python manage.py createsuperuser
   ```
   so you have a login for the deployed admin site.

Your app will be live at `https://epms-XXXX.onrender.com` (Render
assigns the exact subdomain). It's on HTTPS by default.

Note: on the free plan the service sleeps after 15 minutes of
inactivity, so the first request after a break takes 30-50 seconds to
wake up. Fine for now - upgrade to a paid instance ($7/mo) when this
needs to stay warm for real users.
