# Verve Reimbursements

Employee expense reimbursement module for Verve HRMS. Employees submit a monthly claim with bills, their manager approves it, Accounts verifies and pays it, and every step is logged.

Spec: https://claude.ai/artifact/PCQWBkRtFJMeJB6FqEKNd2

## Project structure

```
backend/            FastAPI + SQLAlchemy 2 + Alembic
  app/
    api/            thin HTTP routes
    services/       status machine, permissions, policy warnings, payouts, email, storage
    models.py       database tables
    schemas.py      request/response models (mirrored in frontend/src/types.ts)
  alembic/          database migrations
  tests/            pytest suite
  seed.py           demo data (dev only, wipes the DB)
frontend/           React 18 + Vite + TypeScript
  src/
    pages/          one file per screen
    components/     shared UI (dialog, toast, bill viewer, tables)
docker-compose.yml  local Postgres for testing
```

## Run locally

Backend (Python 3.12):

```
cd backend
py -3.12 -m venv venv
venv\Scripts\python -m pip install -r requirements-dev.txt
venv\Scripts\alembic upgrade head
venv\Scripts\python seed.py
venv\Scripts\python -m uvicorn app.main:app --port 8000
```

Frontend (Node 20+), in a second terminal:

```
cd frontend
npm install
npm run dev
```

Open http://localhost:5173 and pick a test user. `seed.py` resets the local database and loads a demo team with three months of claims in every status. Good starting points: Priya (employee), Rohan (manager), Meera (Accounts) and Aditi (admin).

## Deployment

- Frontend: Vercel, root directory `frontend`, env `VITE_API_URL` = the API origin. https://verve-reimbursement.vercel.app
- API: Render, from `render.yaml` (migrations run on start). Set `DATABASE_URL` to the Neon connection string.
- Database: Neon Postgres.

## Tests

```
cd backend && venv\Scripts\python -m pytest -q
cd frontend && npx tsc -b
```

To run the backend tests on Postgres: `docker compose up -d db`, then set `TEST_DATABASE_URL=postgresql+psycopg://reimb:reimb@localhost:5434/reimb`.

## Not yet done

- Company SSO (Google or Microsoft). Development sign-in only for now.
- Bills are stored on local disk; production needs Supabase Storage or S3.
- Rupee limits for categories and cash-without-bill, from Accounts.
- Later items in spec section 5: delegation, reminders and escalation, phone OCR, second-level approval.
