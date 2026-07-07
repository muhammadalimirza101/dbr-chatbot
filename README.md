# DBR WhatsApp AI Chatbot

WhatsApp AI chatbot and admin dashboard for Destination Beach Resort by Dreamworld (Manora Island, Karachi).

Three services:

| Directory    | Stack                          | Role |
|--------------|--------------------------------|------|
| `backend/`   | Python FastAPI + PostgreSQL    | All business logic, AI pipeline, API |
| `connector/` | Node.js + TypeScript (Baileys) | WhatsApp transport only (swappable for Cloud API) |
| `dashboard/` | React + Vite                   | Staff admin dashboard |

## Quick start (backend, Phase 0)

1. Copy `.env.example` to `.env` at the repo root and fill in real values. **Never commit `.env`.**
2. ```powershell
   cd backend
   python -m venv .venv          # once
   .\.venv\Scripts\pip install -r requirements.txt
   .\.venv\Scripts\uvicorn app.main:app --reload
   ```
3. Verify: `http://127.0.0.1:8000/health` → `{"status":"ok"}` and
   `http://127.0.0.1:8000/health/db` → `{"status":"ok","database":"reachable"}` against your local PostgreSQL.

Full setup, WhatsApp pairing, seeding, and the Baileys → Cloud API migration plan will be documented here in Phase 6.
