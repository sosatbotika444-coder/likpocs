# RS Best Hostel

RS Best Hostel is a full-stack dormitory operations app. The React/TypeScript client is in `frontend/`; the FastAPI service, SQLAlchemy models, Alembic migrations, and pytest suite are in `backend/`. PostgreSQL is the persistent database. The interface is Uzbek (Latin) and uses the Uzbekistan time zone by default.

## Start the full stack with Docker Compose

1. Install Docker Desktop or Docker Engine with the Compose plugin.
2. Copy `.env.example` to `.env` and set unique random values for `POSTGRES_PASSWORD`, `JWT_SECRET` (at least 32 characters), and `INITIAL_OPERATOR_PASSWORD` (at least 12 characters). For Compose, use an alphanumeric PostgreSQL password so its connection URL stays valid. For a direct local `DATABASE_URL`, percent-encode reserved password characters. Set the operator email and display name too. Keep `.env` private.
3. From this directory, run:

   ```powershell
   docker compose up --build -d
   ```

4. Open <http://localhost:8080> and sign in with `INITIAL_OPERATOR_EMAIL` and `INITIAL_OPERATOR_PASSWORD`.

The first API startup applies the database migration and creates the initial operator. PostgreSQL data is held in the `dormflow_postgres` named volume. To stop the stack without deleting data, run `docker compose down`. To intentionally remove the database volume as well, run `docker compose down -v`.

## Local development without Docker

Requirements: Python 3.13, Node.js 24 LTS with npm, and PostgreSQL 17. Create a PostgreSQL database and user, then:

1. Copy `.env.example` to `.env`; update the database URL, JWT secret, and initial operator password.
2. In PowerShell, create a Python environment and install the backend requirements:

   ```powershell
   py -3.13 -m venv .venv
   .\.venv\Scripts\Activate.ps1
   python -m pip install -r backend\requirements.txt
   ```

3. Apply the migration and create the operator:

   ```powershell
   cd backend
   alembic upgrade head
   python -m app.seed
   cd ..
   ```

4. In one terminal, run `python main.py` from the repository root. The API is available at <http://127.0.0.1:8000>; its OpenAPI page is at <http://127.0.0.1:8000/docs>.
5. In another terminal, install and start the frontend:

   ```powershell
   cd frontend
   npm install
   npm run dev
   ```

   Open <http://localhost:5173>. Vite proxies `/api` to the local FastAPI service.

## Configuration

See `.env.example` for the supported variables. Important settings:

| Variable | Purpose |
| --- | --- |
| `DATABASE_URL` | SQLAlchemy PostgreSQL connection string |
| `JWT_SECRET` | Signs access and refresh tokens; use a unique secret in each environment |
| `INITIAL_OPERATOR_EMAIL`, `INITIAL_OPERATOR_PASSWORD`, `INITIAL_OPERATOR_NAME` | Creates the first operator on seed/bootstrap |
| `ACCESS_TOKEN_MINUTES`, `REFRESH_TOKEN_DAYS` | Token lifetime |
| `TIMEZONE` | Billing and date boundary, defaults to `Asia/Tashkent` |
| `ADMINS_CAN_ADJUST_BILLING` | Lets administrators change billing configuration when explicitly enabled |
| `CORS_ORIGINS` | Comma-separated trusted browser origins |
| `PUBLIC_APP_URL` | Public frontend origin used for invitation links; defaults to `https://dormflows.netlify.app` and ignores stale localhost values |
| `FILE_STORAGE_BACKEND`, `S3_*`, `FILE_RETENTION_DAYS` | Private file storage backend and retention period (365 days by default) |
| `OCR_ENABLED`, `OCR_BINARY`, `OCR_LANGUAGES` | Local OCR switch, Tesseract executable, and language models (Uzbek Latin/Cyrillic, English, Russian by default) |
| `OCR_MAX_PAGES`, `OCR_PAGE_TIMEOUT_SECONDS`, `OCR_MAX_PIXELS` | Limits OCR workload for uploaded PDFs and images |

The billing convention uses `[start_date, end_date)`: a cycle includes its start date and ends immediately before its end date. The following cycle starts on the preceding cycle's end date. Period extensions update the open cycle and create an immutable billing-change record; they never create a payment. Actual payment records are append-only. Operators correct them by adding a signed adjustment with a reason.

## Roles

- **Operator:** full access, including administrator accounts, application settings, audit history, and financial adjustments.
- **Administrator:** resident and room operations, payment recording, balances, and reports. Administrators cannot manage accounts, inspect the audit log, adjust historical payments, or change billing settings unless the billing configuration flag is enabled.

Authorization is checked by the API. Hiding a button in the browser is not the access control boundary.

## Admissions and room assignment

Operators create dormitories and admission campaigns. Administrators and operators can issue limited invitations, review applications, request missing information, inspect uploaded files, and approve a room stay. Approval creates or links a resident, records the dated residence period, and opens the first billing period using the existing resident's terms or the selected room's per-bed price and the configured default period. Set each room's price in **Xonalar** for tariff selection to be automatic; an operator can enter an agreed tariff in the approval form when needed. If a linked resident already has an open billing period, approval keeps it and does not create a duplicate charge.

The **Statistika** tab in **Qabul va arizalar** shows application counts, open charges, remaining balances, and payments received from residents linked to approved applications. Approval creates an amount due, not a cash receipt. Actual income appears only after staff records a payment in **To‘lovlar**; recorded costs and net cash flow for the whole hostel appear in **Boshqaruv paneli** and **Xarajatlar**. Payment provider callbacks are not configured.

Applicants open the invitation at `/apply`. The link secret is carried in the URL fragment and removed before the page exchanges it for a short-lived, HTTP-only session. After the first submission, the applicant receives a one-time access code for later status checks and clarification requests. Only a hash of that code is stored. Staff can issue a replacement after manually checking identity.

Development uses the private `private-files/` directory. Production uses a private PostgreSQL blob table by default, so uploads work without a separate S3 account and survive API restarts. Set `FILE_STORAGE_BACKEND=s3` with a private S3-compatible bucket and credentials when a separate object store is available. `FILE_RETENTION_DAYS` defaults to 365 days and should be set to the organization's approved period. Database backups also contain uploaded documents; keep them private and encrypted. The backend Docker image includes local Tesseract OCR with Uzbek Latin/Cyrillic, English, and Russian models. It extracts text from documents for staff review only; OCR text is never returned by public endpoints, never approves an application, and is cleared when the source file is deleted or purged. OCR work is bounded by page, time, and pixel limits. Face recognition is not used. Antivirus scanning is still not connected, so the admissions screen reports that honestly and staff must inspect the original file.

Files scheduled for deletion are purged in bounded batches. The Railway IaC declares a daily cleanup job at 05:30 Tashkent time; other hosting platforms need an equivalent scheduler:

```powershell
python -m app.purge_expired_files --batch-size 100
```

The purge command logs only aggregate counts. Files in abandoned drafts expire after the configured period; rejected applications are scheduled for deletion after that period; approved application files are scheduled when the linked resident is archived.

## Expenses, scheduled billing, and exports

The Uzbek-language **Xarajatlar** screen records dated expenses with a category, payment method, amount, and receipt/reference. Posted entries are never deleted; an operator can void one with a required reason, and both the record and audit trail remain available. Payment and expense writes accept an `Idempotency-Key`; the browser keeps the same key when retrying an unchanged request.

Billing rollover and due reminders run as a daily backend job. The Railway IaC declares it for 05:00 Tashkent time, after the database migrations are in place; other hosting platforms need an equivalent scheduler:

```powershell
python -m app.scheduled_jobs
```

The command creates due billing periods and per-user reminder rows in one database transaction. The schedules take effect when the Railway IaC is applied; they run at 00:00 and 00:30 UTC (05:00 and 05:30 in Tashkent). Rerunning a billing job is safe. GET requests do not create billing periods or notifications. A paid cycle rolls forward on this job; do not rely on page visits to generate charges.

Authorized users can export resident, room, payment, expense, debt, overdue, and revenue reports to UTF-8 CSV, XLSX, and PDF. Revenue reports accept a custom date range and day/week/month grouping. Spreadsheet exports neutralize formula-like text in cells. The optional command `python -m app.seed --demo` creates three sample rooms only; demo residents, payments, and expenses are never inserted.

## Tests

From `backend/`, run:

```powershell
..\.venv\Scripts\python.exe -m pytest tests -q
```

The tests use isolated in-memory SQLite and cover role restrictions, room capacity and dated assignments, admission invitations and review, OCR privacy and file cleanup, private file access, arbitrary billing periods, payment allocation, extensions, idempotent requests, expense voiding, export safety, and financial corrections. The release database remains PostgreSQL.

## Production deployment

Use HTTPS termination at a trusted reverse proxy or managed ingress, keep `PUBLIC_APP_URL=https://dormflows.netlify.app`, restrict `CORS_ORIGINS`, use strong independent secrets, restrict access to the PostgreSQL network, and back up the PostgreSQL volume on a schedule. Production admission uploads use the private PostgreSQL blob table unless `FILE_STORAGE_BACKEND=s3` is explicitly configured. Set `FILE_RETENTION_DAYS` to the organization's approved period before accepting real applications. Configure monitoring against `/api/health`. Build and deploy immutable images from a reviewed commit; do not publish `.env` or database backups with the repository. Set `ENVIRONMENT=production` so the API rejects placeholder JWT secrets and a missing operator password.

The included Compose file is a single-host deployment baseline. For a production service, add an external TLS ingress, automated encrypted off-host backups, and a controlled migration/rollback procedure appropriate to the hosting platform.

## Railway (API + PostgreSQL) and Netlify (frontend)

Deployment files are included for the GitHub repository `sosatbotika444-coder/likpocs`. Push the deployment changes to the `main` branch before connecting the services. Railway's configuration is an Infrastructure as Code project definition: apply it only to a new, empty Railway project because it manages the complete Railway environment.

### Railway

1. Install the Railway CLI and log in:

   ```powershell
   npm.cmd install -g @railway/cli
   railway login
   ```

2. From the repository root, run the one-time setup script:

   ```powershell
   powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\deploy-railway.ps1
   ```

   It creates/links a new Railway project, asks for the first operator's email, name, and password, generates a private JWT signing key, and applies `.railway/railway.ts`. Railway provisions PostgreSQL, links its `DATABASE_URL` to the API, runs Alembic migrations and the idempotent operator bootstrap before the API starts, and checks `/api/health`. The operator password is read securely and the signing key is generated in memory; neither is written to the repository.

3. The setup script attempts to create the API's public HTTPS domain. If the deployment is not ready yet, create it after deployment:

   ```powershell
   railway domain --service dormflow-api
   ```

   Keep the resulting `https://….up.railway.app` address for the Netlify setup. Do not expose PostgreSQL publicly. Railway provides the PostgreSQL `DATABASE_URL` through an inter-service variable reference; the backend converts Railway's `postgres://`/`postgresql://` scheme to the installed psycopg 3 SQLAlchemy driver automatically.

### Netlify

1. Install and authenticate the Netlify CLI, then connect this repository to a new Netlify site from the repository root:

   ```powershell
   npm.cmd install -g netlify-cli
   netlify login
   netlify init
   ```

   Netlify reads the root `netlify.toml`: base directory `frontend`, Node.js 24, `npm ci`, the TypeScript/Vite production build, and the `dist` publish directory.

2. Run the production setup/deploy script and paste in the Railway API domain when asked:

   ```powershell
   powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\deploy-netlify.ps1
   ```

   This sets the `RAILWAY_API_URL` build variable for all Netlify deploy contexts, builds the frontend, writes the API proxy and SPA fallback to `dist/_redirects`, then deploys production. The browser continues calling same-origin `/api`; Netlify forwards that path to Railway, so the frontend build does not need a hardcoded API address or CORS allowlist. Keep `RAILWAY_API_URL` as the HTTPS origin only (no `/api` suffix).

After setup, GitHub pushes to `main` trigger builds on both providers. Railway uses `backend/` as the API root and Netlify uses `frontend/` as its build base. The Railway setup script is for a new project bootstrap; routine code releases should use the connected GitHub autodeploys. For a changed API domain, update `RAILWAY_API_URL` in Netlify and redeploy.

Before using real resident and payment data, enable PostgreSQL backups/point-in-time recovery appropriate to the Railway plan and verify a restore procedure. Database backups are not stored in this repository.
