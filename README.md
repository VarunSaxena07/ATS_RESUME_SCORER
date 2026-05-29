# ATS Resume Scorer

An AI-powered resume analysis app that scores resumes for applicant tracking system
compatibility, compares resumes against job descriptions, validates listed skills
against project and experience evidence, and exports report PDFs.

The project has two main parts:

- `backend/`: FastAPI service for parsing resumes, running analysis, saving history,
  and generating PDFs.
- `frontend/`: Streamlit app for authentication, resume upload, score dashboards,
  history, and report downloads.

## Features

- Upload resumes in PDF, DOC, or DOCX format.
- Score resumes across formatting, keywords, content quality, skill validation,
  and ATS compatibility.
- Compare a resume with an optional job description using keyword overlap and
  semantic similarity.
- Detect missing sections, weak bullets, unsupported skills, missing metrics, and
  other resume issues.
- Validate whether skills are backed by projects or experience.
- Save per-user analysis history in Supabase.
- Export current or historical analysis results as PDF reports.
- Supports email/password and Google OAuth sign-in through Supabase.

## Tech Stack

- Python
- FastAPI
- Streamlit
- Supabase Auth and REST API
- spaCy
- SentenceTransformers
- Groq Llama model for structured resume and job description parsing
- pdfplumber, PyPDF2, and python-docx for file extraction
- Jinja2 and WeasyPrint for PDF generation

## Project Structure

```text
.
+-- backend/
|   +-- api/                 # FastAPI routes and auth helpers
|   +-- core/                # App configuration
|   +-- database/            # Supabase persistence helpers
|   +-- models/              # Pydantic response schemas
|   +-- services/            # Parsing, scoring, matching, reports
|   +-- templates/           # HTML templates for PDF reports
|   +-- main.py              # FastAPI app entry point
+-- frontend/
|   +-- assets/              # Streamlit CSS
|   +-- components/          # Dashboard and result UI components
|   +-- services/            # API and Supabase clients
|   +-- views/               # Streamlit views
|   +-- streamlit_app.py     # Streamlit app entry point
+-- streamlit_app.py         # Root launcher for Streamlit Cloud
+-- requirements.txt         # Full app dependencies
+-- backend/requirements.txt # Backend-only dependencies
```

## Prerequisites

- Python 3.10 or newer
- A Supabase project
- A Groq API key
- Optional but recommended: a virtual environment

PDF export uses WeasyPrint. If PDF generation fails during installation or runtime,
install the native dependencies required by WeasyPrint for your operating system.

## Setup

Create and activate a virtual environment:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

Install dependencies:

```powershell
pip install -r requirements.txt
```

The spaCy model is installed from `requirements.txt`. If you install dependencies
manually, make sure `en_core_web_sm` or `en_core_web_md` is available.

## Environment Variables

Create a `.env` file in the project root. The backend also checks `backend/.env`,
but keeping one root `.env` is usually simpler.

```env
GROQ_API_KEY=your_groq_api_key

SUPABASE_URL=https://your-project.supabase.co
SUPABASE_ANON_KEY=your_supabase_anon_key
SUPABASE_API_KEY=your_supabase_service_role_key

# Required only when your Supabase JWTs use HS256.
SUPABASE_JWT_SECRET=your_supabase_jwt_secret

# Optional. Used by Google OAuth redirect in the Streamlit app.
AUTH_REDIRECT_URL=http://localhost:8501

# Optional. Defaults to all-MiniLM-L6-v2.
SENTENCE_TRANSFORMER_MODEL=all-MiniLM-L6-v2
```

For Streamlit Cloud or another hosted frontend, you can also configure secrets:

```toml
[backend]
url = "https://your-backend.example.com"

[supabase]
SUPABASE_URL = "https://your-project.supabase.co"
SUPABASE_ANON_KEY = "your_supabase_anon_key"

[google_oauth]
redirect_uri = "https://your-streamlit-app.streamlit.app"
```

## Supabase Table

The backend stores analysis history in an `analyses` table. A minimal schema is:

```sql
create table if not exists analyses (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null,
  filename text,
  ats_score numeric,
  keyword_match numeric,
  missing_keywords jsonb default '[]'::jsonb,
  analysis_result jsonb not null,
  created_at timestamptz default now()
);

create index if not exists analyses_user_created_idx
  on analyses (user_id, created_at desc);
```

The backend writes with `SUPABASE_API_KEY`, which should be a service-role key and
must never be exposed to the frontend.

## Run Locally

Start the backend API:

```powershell
uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
```

In another terminal, start the Streamlit frontend:

```powershell
streamlit run streamlit_app.py
```

Open the frontend at:

```text
http://localhost:8501
```

The frontend defaults to the backend at `http://localhost:8000`. For a deployed
frontend, set `st.secrets["backend"]["url"]`.

## API Endpoints

Base URL:

```text
http://localhost:8000
```

Endpoints:

- `GET /` - API metadata and available routes.
- `GET /api/v1/health` - confirms NLP models are loaded.
- `POST /api/v1/analyze-resume` - analyzes a resume file and optional job description.
- `GET /api/v1/history` - returns the signed-in user's saved analyses.
- `DELETE /api/v1/history/{analysis_id}` - deletes one saved analysis.
- `POST /api/v1/generate-pdf` - generates a PDF from an analysis payload.
- `GET /api/v1/history/{analysis_id}/pdf` - generates a PDF for a saved analysis.

All `/api/v1/*` endpoints except health require:

```text
Authorization: Bearer <supabase_access_token>
```

Interactive API docs are available while the backend is running:

```text
http://localhost:8000/docs
```

## Typical Workflow

1. Sign in or create an account from the Streamlit sidebar.
2. Open the ATS Scorer page.
3. Upload a resume file.
4. Choose either a general ATS score or a job description comparison.
5. Run the analysis.
6. Review the dashboard, detailed feedback, and skill validation.
7. Download a PDF or text summary.
8. Revisit previous analyses from the History page.

## Troubleshooting

### Backend cannot parse resumes

Check that `GROQ_API_KEY` is set. Resume and job description parsing depends on
the Groq client in `backend/services/groq_parser.py`.

### Frontend says it cannot reach the backend

Make sure the API is running on port `8000`:

```powershell
uvicorn backend.main:app --reload --port 8000
```

For hosted frontends, set the backend URL in Streamlit secrets.

### Sign-in works but API calls return 401

Check `SUPABASE_URL`. The backend uses it to fetch Supabase JWKS for JWT
verification. If your project uses HS256 tokens, also set `SUPABASE_JWT_SECRET`.

### History does not save

Check `SUPABASE_API_KEY` and confirm the `analyses` table exists. The analysis
request can still succeed even if history saving fails.

### PDF generation fails

Verify WeasyPrint is installed correctly and that your operating system has the
native libraries it needs.

## Notes

- Maximum backend resume file size is configured as 5 MB.
- Streamlit upload size is configured in `.streamlit/config.toml`.
- Supported resume extensions are `.pdf`, `.doc`, and `.docx`.
- Job description uploads in the frontend currently support `.txt`; PDF/DOCX job
  descriptions should be pasted as text.
