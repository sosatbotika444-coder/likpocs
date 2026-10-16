# DormFlow

DormFlow is a full-stack dormitory operations app. The React/TypeScript client is in `frontend/`; the FastAPI service, SQLAlchemy models, Alembic migrations, and pytest suite are in `backend/`. PostgreSQL is the persistent database. The interface is Uzbek (Latin) and uses the Uzbekistan time zone by default.

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

The billing convention uses `[start_date, end_date)`: a cycle includes its start date and ends immediately before its end date. The following cycle starts on the preceding cycle's end date. Period extensions update the open cycle and create an immutable billing-change record; they never create a payment. Actual payment records are append-only. Operators correct them by adding a signed adjustment with a reason.

## Roles

- **Operator:** full access, including administrator accounts, application settings, audit history, and financial adjustments.
- **Administrator:** resident and room operations, payment recording, balances, and reports. Administrators cannot manage accounts, inspect the audit log, adjust historical payments, or change billing settings unless the billing configuration flag is enabled.

Authorization is checked by the API. Hiding a button in the browser is not the access control boundary.

## Data exports and optional sample rooms

Authorized users can export resident, room, payment, debt, overdue, and revenue reports to UTF-8 CSV, XLSX, and PDF. Revenue reports accept a custom date range and day/week/month grouping. The optional command `python -m app.seed --demo` creates three sample rooms only; demo residents or payments are never inserted.

## Tests

From `backend/`, run:

```powershell
..\.venv\Scripts\python.exe -m pytest tests -q
```

The tests use isolated in-memory SQLite and cover role restrictions, room capacity, arbitrary billing periods, payment allocation, extensions, and financial corrections. The release database remains PostgreSQL.

## Production deployment

Use HTTPS termination at a trusted reverse proxy or managed ingress, restrict `CORS_ORIGINS`, use strong independent secrets, restrict access to the PostgreSQL network, and back up the PostgreSQL volume on a schedule. Configure monitoring against `/api/health`. Build and deploy immutable images from a reviewed commit; do not publish `.env` or database backups with the repository. Set `ENVIRONMENT=production` so the API rejects placeholder JWT secrets and a missing operator password.

The included Compose file is a single-host deployment baseline. For a production service, add an external TLS ingress, automated encrypted off-host backups, and a controlled migration/rollback procedure appropriate to the hosting platform.
