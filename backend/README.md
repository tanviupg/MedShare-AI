# MedShare AI backend

FastAPI and SQLAlchemy foundation for MedShare AI, including authentication, user management, and donor medicine submissions.

## Requirements

- Python 3.10–3.12 on Windows (PaddlePaddle's Windows wheels are not available for Python 3.13+)
- PostgreSQL for database-backed work (not needed to start the API)

## Setup

From `backend/`, create and activate a virtual environment, then install dependencies:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
```

Edit `DATABASE_URL` in `.env` for your PostgreSQL instance when you are ready to run database migrations. Importing or starting the API does not connect to the database.
Set `JWT_SECRET` to a long random value before using authentication. `JWT_ALGORITHM` and `JWT_EXPIRATION_MINUTES` are also configurable. Medicine image extraction uses Gemini 2.5 Flash by default; set `GEMINI_API_KEY` in the backend environment. `GEMINI_MODEL` can select another supported Gemini model. Set `MEDICINE_EXTRACTION_PROVIDER=paddleocr` to use the retained local PaddleOCR fallback. The pharmacist must still verify extracted fields against the package; OCR never approves a donation.

## Run

```powershell
uvicorn app.main:app --reload
```

The health endpoint is `GET http://localhost:8000/health`. Authentication endpoints are `POST /auth/signup`, `POST /auth/login`, and `GET /auth/me`.

Donors can submit medicine details with `POST /donations`, list their submissions with `GET /donations/mine`, and retrieve one owned submission with `GET /donations/{donation_id}`. Attach up to eight JPEG, PNG, or WebP images (5 MB each) using multipart `POST /donations/{donation_id}/images` with repeated `files` fields. Image metadata is returned with an authenticated download URL; local image bytes are stored under `UPLOAD_DIR` (defaults to `uploads/`). Every new submission starts at `PENDING_REVIEW`. Review state changes are not exposed yet.

## Migrations

Alembic is configured to use `DATABASE_URL` from `.env` and `Base.metadata` from `app.db.base`. Database migration commands require a reachable PostgreSQL database:

```powershell
alembic upgrade head
```

Migrations create and evolve the application schema. Revision `20261004_0015` repairs a missing `donations.packaging_type` column in databases whose migration version was advanced without that column.

## Clinic verification

Clinic profiles start as `PENDING`. An authenticated platform administrator can review pending clinic details in the admin frontend or through `GET /admin/clinic-verifications/pending`, then approve with `POST /admin/clinic-verifications/{clinic_profile_id}/approve` or reject with a non-empty `reason` using `POST /admin/clinic-verifications/{clinic_profile_id}/reject`. Decisions record the administrator and timestamp. This records the platform's decision; review of submitted license details remains a manual operational step.

Public signup does not offer the `ADMIN` role. After applying migrations, an authorized operator can provision an initial administrator from `backend/` with `python -m app.cli.create_admin reviewer@example.com --name "Platform Reviewer"`. The command prompts for a password without echoing it and stores only its hash. Administrators then sign in through the normal login page; never create an administrator through public signup or commit credentials to configuration or source.
