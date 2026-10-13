# MedShare AI

**An AI-assisted medicine donation and redistribution platform**

MedShare AI helps donors submit unused medicines for review by verified clinics, so eligible medicines can be made available to patients who need them. The platform supports medicine image extraction, pharmacist verification, inventory management, patient requests, and clinic verification.

> **Important:** AI-based OCR only extracts medicine information. It does not approve donations, diagnose patients, or prescribe medicines. A pharmacist must verify the extracted information and medicine packaging.

## Table of Contents

- [Features](#features)
- [Technology Stack](#technology-stack)
- [Prerequisites](#prerequisites)
- [Project Structure](#project-structure)
- [Getting Started](#getting-started)
- [Environment Configuration](#environment-configuration)
- [Running the Application](#running-the-application)
- [Database Migrations](#database-migrations)
- [Authentication and User Roles](#authentication-and-user-roles)
- [Clinic Verification](#clinic-verification)
- [Medicine Donations and Images](#medicine-donations-and-images)
- [API Endpoints](#api-endpoints)
- [Security Notes](#security-notes)
- [Troubleshooting](#troubleshooting)

## Features

- **Donor management:** Submit unused medicines and upload medicine package images.
- **Medicine information extraction:** Use Gemini 2.5 Flash or the retained local PaddleOCR option to extract information from medicine images.
- **Pharmacist verification:** Review extracted medicine details and verify donations before approval.
- **Clinic verification:** Allow platform administrators to approve or reject clinic registrations.
- **Inventory management:** Manage approved medicines and their availability.
- **Patient requests:** Support medicine discovery and requests according to the platform's verification rules.
- **Authentication:** Secure login and role-based access for donors, patients, clinic pharmacists, and administrators.
- **Database migrations:** Manage database schema changes through Alembic.

## Technology Stack

| Component | Technology |
|---|---|
| Frontend | React, TypeScript, Vite |
| Backend | Python, FastAPI |
| ORM | SQLAlchemy |
| Database | PostgreSQL |
| Database migrations | Alembic |
| Authentication | JWT |
| Medicine OCR | Gemini 2.5 Flash |
| Alternative OCR | PaddleOCR |

## Prerequisites

Install the following before running the application:

- **Python 3.12** recommended for the backend environment described here. The project setup specifies Python 3.10–3.12 for Windows because PaddlePaddle Windows wheels may not be available for newer Python versions.
- **Node.js and npm** for the frontend.
- **PostgreSQL** for database-backed features and migrations.
- **Google AI Studio API key** for Gemini-based medicine extraction.
- **Git** if you are cloning the repository.

PostgreSQL is required for database migrations and database-backed workflows. Starting the API may be possible without a reachable database, but authentication and other database-dependent features will require the database to be configured and available.

## Project Structure

```text
newMed/
├── backend/
│   ├── app/
│   │   ├── api/
│   │   ├── cli/
│   │   ├── core/
│   │   ├── db/
│   │   └── models/
│   ├── alembic/
│   ├── tests/
│   ├── requirements.txt
│   ├── .env.example
│   └── .env
│
└── frontend/
    ├── src/
    ├── public/
    ├── package.json
    └── ...
```

*The exact contents may vary as development continues.*

## Getting Started

### 1. Open the project

If the repository is already on your computer, open PowerShell in the project directory:

```powershell
cd D:\newMed
```

### 2. Configure the backend environment

Open a PowerShell terminal and run:

```powershell
cd D:\newMed\backend

python -m venv .venv
.\.venv\Scripts\Activate.ps1

python -m pip install --upgrade pip
pip install -r requirements.txt

Copy-Item .env.example .env
```

If `.venv` already exists and contains the required dependencies, you do not need to recreate it. If `.env` already exists, **do not overwrite it**; edit the existing file instead.

### 3. Configure the frontend

Open a **second terminal**:

```powershell
cd D:\newMed\frontend
npm install
```

## Environment Configuration

Edit `backend/.env` and configure the variables supported by your backend configuration.

### Database

Set `DATABASE_URL` to your PostgreSQL connection string. For example:

```dotenv
DATABASE_URL=postgresql+psycopg://USERNAME:PASSWORD@localhost:5432/medshare
```

Replace the example values with your PostgreSQL username, password, host, and database name. Ensure the database exists and PostgreSQL is running before applying migrations.

### JWT authentication secret

Generate a strong random secret in PowerShell:

```powershell
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Copy the generated value into `backend/.env` using the variable name expected by the application:

```dotenv
JWT_SECRET=PASTE_YOUR_GENERATED_SECRET_HERE
```

Keep the generated value private. Do not put it in frontend environment variables or commit it to GitHub.

The backend also supports `JWT_ALGORITHM` and `JWT_EXPIRATION_MINUTES`, according to the current configuration. Keep the algorithm consistent with the backend's supported settings.

### Gemini API key

Gemini is the default medicine extraction provider.

1. Open [Google AI Studio](https://aistudio.google.com/apikey).
2. Create or obtain an API key.
3. Add it to `backend/.env`:

```dotenv
GEMINI_API_KEY=YOUR_GEMINI_API_KEY
GEMINI_MODEL=gemini-2.5-flash
```

Use the actual variable names defined in `.env.example` and the backend configuration.

To use the retained local OCR alternative, configure:

```dotenv
MEDICINE_EXTRACTION_PROVIDER=paddleocr
```

PaddleOCR may require its own compatible Python environment and installed dependencies. The Gemini provider requires a valid API key and available API quota.

**Never commit your `.env` file, JWT secret, database password, or API keys.**

## Running the Application

Start the backend and frontend in **separate terminals**.

### Terminal 1: Backend

```powershell
cd D:\newMed\backend
.\.venv\Scripts\Activate.ps1

alembic upgrade head
uvicorn app.main:app --reload
```

The backend should be available at:

- API base URL: `http://127.0.0.1:8000`
- Health endpoint: `http://127.0.0.1:8000/health`
- Interactive API documentation: `http://127.0.0.1:8000/docs`

The health endpoint is `GET /health`.

### Terminal 2: Frontend

```powershell
cd D:\newMed\frontend
npm run dev
```

Open the local URL printed in the terminal, usually:

`http://localhost:5173`

If the frontend cannot connect to the backend, check its API base URL configuration and confirm that the backend is running.

## Database Migrations

MedShare AI uses Alembic to create and update the database schema.

After configuring PostgreSQL and `DATABASE_URL`, run:

```powershell
cd D:\newMed\backend
.\.venv\Scripts\Activate.ps1
alembic upgrade head
```

Useful migration commands:

**Check the current database revision**

```powershell
alembic current
```

**View migration history**

```powershell
alembic history
```

Apply migrations whenever the application introduces a schema change. Back up important data before applying migrations to a database containing data you need to preserve.

The project includes a migration identified as `20261004_0015` that repairs a missing `donations.packaging_type` column in databases whose recorded migration version had advanced without that column.

## Authentication and User Roles

The platform supports these roles:

- **DONOR:** Submits medicine donations and views their own submissions.
- **PATIENT:** Discovers eligible medicines and submits requests.
- **CLINIC_PHARMACIST:** Reviews donations and manages clinic medicine workflows.
- **ADMIN:** Reviews clinic verification applications and performs authorized platform-level operations.

Public signup must not allow users to create an administrator account by selecting the `ADMIN` role.

### Authentication endpoints

| Method | Endpoint | Purpose |
|---|---|---|
| `POST` | `/auth/signup` | Register a supported user account |
| `POST` | `/auth/login` | Authenticate and obtain a token |
| `GET` | `/auth/me` | Retrieve the authenticated user's information |

Send the authentication token with protected requests using the standard bearer-token header:

```http
Authorization: Bearer YOUR_ACCESS_TOKEN
```

### Provisioning the first administrator

After applying database migrations, run the following from `backend/`:

```powershell
python -m app.cli.create_admin reviewer@example.com --name "Platform Reviewer"
```

The command prompts for a password without echoing it and stores its hash. Use an authorized operator to provision this account; never create an administrator through public signup or commit administrator credentials to source control.

## Clinic Verification

New clinic profiles start with a `PENDING` verification status. An authenticated platform administrator can review pending clinic applications through the admin interface or API.

| Method | Endpoint | Purpose |
|---|---|---|
| `GET` | `/admin/clinic-verifications/pending` | List pending clinic applications |
| `POST` | `/admin/clinic-verifications/{clinic_profile_id}/approve` | Approve a clinic |
| `POST` | `/admin/clinic-verifications/{clinic_profile_id}/reject` | Reject a clinic with a non-empty reason |

Approval and rejection record the administrator and decision timestamp.

This process records the platform's review decision. It does not represent automatic or external regulatory verification of a clinic's license; submitted license details still require manual operational review.

## Medicine Donations and Images

Donors can submit medicine donations, view their own submissions, and attach package images.

### Donation endpoints

| Method | Endpoint | Purpose |
|---|---|---|
| `POST` | `/donations` | Create a donation submission |
| `GET` | `/donations/mine` | List the authenticated donor's submissions |
| `GET` | `/donations/{donation_id}` | Retrieve an owned donation submission |
| `POST` | `/donations/{donation_id}/images` | Upload images for a donation |

### Image upload requirements

- Maximum of **8 images** per upload request.
- Accepted formats: JPEG, PNG, and WebP.
- Maximum size: **5 MB per image**.
- Use multipart form data with repeated `files` fields.

New donations begin with the `PENDING_REVIEW` status. Image metadata is returned with an authenticated download URL, and image bytes are stored under `UPLOAD_DIR`, which defaults to `uploads/`.

Medicine images must be accessed through authorized application endpoints. Do not expose private medicine images through public static URLs.

The pharmacist must physically verify medicine details and packaging before approving a donation. OCR output alone never approves a donation.

## API Endpoints

Interactive documentation is available at:

`http://127.0.0.1:8000/docs`

The API includes authentication, donation submissions, clinic verification, medicine review, inventory, and patient workflows. Refer to the interactive documentation for the current request schemas, response formats, and authorization requirements.

## Security Notes

- Keep secrets and credentials in backend environment variables.
- Do not commit `.env` files or API keys.
- Never expose donor pickup addresses to patients.
- Restrict private medicine images and records to authorized users.
- Enforce role-based authorization on backend endpoints; hiding a frontend control is not sufficient security.
- Only verified clinics should access workflows that expose donor-private review data, according to the platform's verification policy.
- Use HTTPS, restrictive CORS settings, secure secret storage, and database backups for deployment.
- Verify legal, privacy, medicine-handling, and disposal requirements before using the platform in a real-world setting.

## Troubleshooting

### `alembic upgrade head` fails

- Confirm PostgreSQL is running.
- Verify `DATABASE_URL` in `backend/.env`.
- Confirm the database exists and your credentials are correct.

### Authentication fails

- Confirm `JWT_SECRET` matches the variable name expected by the backend.
- Ensure the backend has loaded the intended `.env` file.
- Check that the database is available and migrations are applied.

### Medicine extraction fails

- Confirm `GEMINI_API_KEY` is configured correctly.
- Check API quota and connectivity.
- Confirm `GEMINI_MODEL` is supported.
- If using PaddleOCR, verify that the appropriate environment and dependencies are installed.

### Frontend cannot connect to the backend

- Confirm the backend is running at `http://127.0.0.1:8000`.
- Check the frontend's API base URL.
- Inspect browser developer tools and the backend terminal for errors.

---

**MedShare AI — safer medicine redistribution through verified workflows and responsible AI-assisted extraction.**
