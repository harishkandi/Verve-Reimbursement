# Verve Reimbursement Module

Employee reimbursement feature for Verve HRMS: replaces the monthly reimbursement spreadsheet.

## Sources of truth
- **Spec (Draft v0.3, all decisions final):** https://claude.ai/artifact/PCQWBkRtFJMeJB6FqEKNd2. Read it with the Claude Docs tools only when a detail isn't in this file.
- `Reimbursement Document.docx`: the original one-page note (v0.1), now superseded by the spec. Don't re-read it.

## Stack and layout
Same stack as Verveflow (adminsoftware-alt/Verve-clickup): FastAPI + SQLAlchemy 2 + Alembic backend, React 18 + Vite + TypeScript frontend. SQLite locally, Postgres in production.
- `backend/app/models.py`: all tables. `services/claims.py`: the status machine and every permission rule; read it before changing workflow. `services/policy.py`: warnings (never block). `services/payouts.py`: batches and exports. `api/`: thin routes. Domain errors in `services/errors.py` map to HTTP codes in `main.py`.
- Emails are queued with `notify.queue()` and sent only by `notify.commit(db)`, after the commit succeeds. Routes must call `commit(db)`, not `db.commit()`.
- `frontend/src/pages/Claim.tsx`: one screen for editing, manager review and Accounts verification, driven by the claim's `allowed_actions` from the API. `types.ts` mirrors `backend/app/schemas.py`; update both together.
- UI: plain CSS in `frontend/src/index.css` using Verveflow's tokens (navy scale around #234788, `--line`/`--ink` neutrals, Inter), `lucide-react` icons. Flat: no hover motion, no tooltips (no `title=`), no `window.confirm` (use `useDialog()` from `components/Dialog.tsx`). Shared pieces live in `components/ui.tsx` (StatusBadge, Person, Stat, Empty, Notice, SkeletonRows, ClaimTable). Money is always `money()` with tabular numbers.
- Action feedback goes through `useToast()` (`components/Toast.tsx`), not inline notices; inline `Notice` is for persistent state (returned/rejected reason, policy warnings, load errors).
- The page's primary action lives in a sticky `.dock` bar (see `pages/Claim.tsx`); bills open in `components/BillViewer.tsx` (side panel, ←/→ between bills), never a new tab.
- Pages with their own header card use `<PageHead crumbsOnly …>` (keeps breadcrumb + browser-tab title). Headings and headline figures use the display face (Plus Jakarta Sans); body text is Inter.
- Check UI changes at 1440px and 390px wide; the page must never scroll sideways on a phone.

## Commands
- Backend tests: `cd backend && venv/Scripts/python -m pytest -q` (SQLite; set `TEST_DATABASE_URL` for Postgres via `docker compose up -d db`).
- Backend server: `cd backend && venv/Scripts/python -m uvicorn app.main:app --port 8000`
- Schema change: edit models, then `venv/Scripts/alembic revision --autogenerate -m "..."` and `venv/Scripts/alembic upgrade head`.
- Demo data: `venv/Scripts/python seed.py` WIPES the DB and loads 9 people + 14 claims in every status (dev only; refuses otherwise). Users are `<firstname>@verve.example`: priya (employee), rohan (manager), meera (Accounts), aditi (admin). `.local`/`.test` emails fail validation. Restart uvicorn after seeding.
- Frontend: `cd frontend && npm run dev` (proxies `/api` to :8000). Type check: `npx tsc -b`; it must be clean.

## Git
- This folder is a standalone local git repo until harishkandi gets access to `adminsoftware-alt/verve-hrms` (private). Then the code moves onto branch `feature/reimbursement` there.
- Use GitHub account **harishkandi** for that repo, not kandiharish.
- Commit or push only when asked.

## Decisions (do not re-open)
- Built in-house (not Zoho Expense, Fyle, etc.).
- **One claim per employee per month**, containing line items: date, category, description, payment mode (Cash/Online), amount, bills.
- Statuses: `Draft → Submitted → ManagerApproved → Verified → InPayoutBatch → Paid`, plus `Returned` (back to the employee, who resubmits to Submitted) and `Rejected` (final). Paid claims are locked.
- Roles: Employee, Manager, Accounts (verifies and pays, with separate permissions), Admin. Nobody approves their own claim; a manager's claim goes to the next manager up; founders' and CXOs' claims go to another founder or the Finance head.
- Manager checks business purpose; Accounts does the detailed bill check. Managers can approve or reject individual line items.
- Approvers may only adjust the *approved* amount, always with a reason; the original amount is kept. Every action goes in an immutable audit log.
- Policy limits **warn only** in v1 and are editable by Admin. Claims due by the 5th of the next month; expenses older than 60 days need Finance approval. Cash without a bill: self-declaration up to a limit (₹ values pending from Accounts).
- INR only; no advances or foreign currency in v1. Optional GSTIN and tax-amount fields.
- Payout: monthly bank transfer, separate from payroll. A payout batch is exported to Excel/CSV, then marked Paid with a payment reference (UTR).
- Reporting lines uploaded by Admin as a CSV. Plan for up to 200 employees. Start fresh; no migration of old sheets.
- Bills: PDF/JPG/PNG, max 10 MB, private storage. Email notifications in v1. Must work in desktop and phone browsers.

## MVP scope
Submission (FR-1–5), manager approval (FR-9–12), Accounts verification (FR-15–17), payout batch/export/mark paid (FR-18–20), status history, audit log and email (FR-21–23), admin and CSV import (FR-25–26).
Later: limit checks, duplicate-bill detection, phone OCR, delegation, second-level approval, reminders and escalation.

## Still open
- ₹ limits per category and for cash without a bill (from Accounts); Admin enters them in the app.
- SSO provider: Google Workspace or Microsoft (from IT). Until then, `/api/auth/dev-login` (dev only).
- Bill storage is local disk (`services/storage.py`); production needs Supabase Storage or S3.
- Never tested on Postgres yet (Docker wasn't running).

## Working style
- Keep replies short. Don't re-derive or restate the decisions above.
- When verve-hrms becomes visible, adopt its auth, user table and conventions rather than keeping parallel ones.
