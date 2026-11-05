# RS Best Hostel — project instructions

## Product and language

- This is the hostel operations system for RS Best Hostel, currently built with React + TypeScript, FastAPI, SQLAlchemy, Alembic, and PostgreSQL.
- Keep all guest-facing and staff-facing website text in Uzbek Latin. Use `frontend/src/locales/uz.ts` for shared labels and format money as UZS (`so'm`).
- Use the `Asia/Tashkent` timezone for business dates. Store timestamps in UTC and convert only at display or business-date boundaries.
- Preserve the existing product structure and migrate incrementally; do not replace the stack or remove working workflows without a written migration path.

## Data and finance

- Represent money as `Decimal` in Python and `NUMERIC(14, 2)` in the database. Never use binary floating point for persisted calculations.
- Keep payments, expenses, adjustments, billing periods, and audit records attributable and traceable. Never hard-delete a posted financial record; use an auditable correction or void.
- Make financial write endpoints transactional and safe to retry. Use idempotency keys for payment creation and lock the affected billing period before checking its balance.
- Record old and new values plus a reason for edits to financial terms. Do not silently rewrite past charges.
- GET endpoints must not create or mutate business records. Put scheduled billing rollover in an explicit command/job or a deliberate write endpoint.
- Add constraints and Alembic migrations for schema changes. Keep migration upgrade and downgrade paths usable on PostgreSQL and the SQLite test schema.

## Access and privacy

- Check authorization on the API, not only in the frontend. Scope personal notifications and private files to the signed-in user/application as appropriate.
- Keep payment-provider, Telegram, cloud-storage, and other secrets on the server. Never add live credentials or `.env` values to source control or browser bundles.
- Do not claim an external integration works until a real provider adapter is configured and its callbacks are verified.
- Keep applicant identity documents private; avoid including their contents in logs, audit details, or exports unless the workflow requires it.

## Changes and verification

- Add or update isolated tests for new rules, especially finance, authorization, migrations, and Uzbek-visible workflows. Never point tests at a production or personal local database.
- Run the frontend typecheck/build after frontend changes and the backend tests after backend changes when dependencies are available.
- Prefer small, reversible schema and UI changes. Keep examples and project prompts aligned with the current implementation.
- Read docs/PROJECT_INDEX.md before changing code. Update it in the same task for every project change: document every new or changed function and API route (including its authorization), data/schema/migration, UI route, cross-layer workflow, integration and configuration setting, plus relevant verification. Keep the file and symbol inventories accurate; correct stale entries instead of appending contradictions. Never copy secrets, .env contents, guest documents or personal data into the index.
