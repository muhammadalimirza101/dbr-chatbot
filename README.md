# DBR WhatsApp AI Chatbot & Dashboard

WhatsApp AI chatbot and staff dashboard for **Destination Beach Resort by Dreamworld** (Manora Island, Karachi). The bot answers guest questions from a knowledge base, guides customers toward bookings, captures leads into a CRM, and hands over to human agents when needed.

| Service      | Stack                                   | Role |
|--------------|-----------------------------------------|------|
| `backend/`   | Python 3.12+ · FastAPI · PostgreSQL 16+ | All business logic, AI pipeline, dashboard API |
| `connector/` | Node 20+ · TypeScript · Baileys v7      | WhatsApp transport only (swappable, see migration plan) |
| `dashboard/` | React · Vite · TanStack Query           | Staff dashboard (agents + admins) |

No Docker, no Postgres extensions (similarity search runs in the backend with numpy).

---

## 1. First-time setup

### Prerequisites
PostgreSQL 16+ running locally with a database created, Python 3.12+, Node 20+.

### Environment
```powershell
Copy-Item .env.example .env    # then fill every value — never commit .env
```
Generate secrets: `python -c "import secrets; print(secrets.token_urlsafe(64))"` (run twice: `JWT_SECRET`, `CONNECTOR_SHARED_SECRET`). `WHATSAPP_SESSION_DIR` **must be outside this repository** — the connector refuses to start otherwise.

### Backend
```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt
.\.venv\Scripts\alembic upgrade head          # create/upgrade schema
$env:SEED_ADMIN_EMAIL = "you@example.com"     # first admin
$env:SEED_ADMIN_PASSWORD = "<strong password>"
.\.venv\Scripts\python -m scripts.seed        # admin + ~16 starter KB entries
```
The starter KB entries contain **TODO placeholders** for prices, timings, and package details — fill them in the dashboard (Knowledge Base) with real information from the resort before launch. The bot is instructed to never invent these facts.

### Connector & dashboard
```powershell
cd connector;  npm install
cd ..\dashboard; npm install
```

### Production database user (do this before going live)
The app must not run as `postgres`. Create the least-privilege role (read/write only, no DDL):
```powershell
psql -U postgres -d dbr_chatbot -f backend\scripts\create_db_user.sql   # edit password first
```
Then point `DATABASE_URL` at `dbr_app`. Keep running Alembic migrations as the owner user.

---

## 2. Running (three terminals)

```powershell
# 1 — backend API
cd backend; .\.venv\Scripts\uvicorn app.main:app --port 8000

# 2 — WhatsApp connector
cd connector; npm run dev

# 3 — dashboard
cd dashboard; npm run dev     # http://localhost:5173
```

### Pairing WhatsApp (one time)
Start the connector, then on the resort's phone: **WhatsApp → Linked devices → Link a device** and scan the QR shown in the terminal. The session persists in `WHATSAPP_SESSION_DIR`; if the terminal ever says "logged out", clear that directory and re-pair. Those session files grant full control of the WhatsApp number — never copy or commit them.

---

## 3. Day-to-day operations

- **Knowledge base** (admin): Dashboard → Knowledge Base. Add Q&A pairs; embeddings are generated automatically on save and the bot uses them immediately. Check the **Unanswered questions** tab regularly — one click converts a missed question into a KB entry.
- **Human takeover**: Conversations → *Take over*. The bot goes silent for that chat (it also hands off automatically when a customer asks for a human, repeats themselves, or sounds frustrated — and flags weddings/corporate as high-value). *Return to bot* resumes automation.
- **Leads**: bot-detected bookings appear automatically with an AI summary; drag cards across stages, assign agents, set follow-ups. The overdue view shows missed follow-ups.
- **Users** (admin): Settings → add agents (`agent` role = conversations + leads only).
- **Media** (admin): Settings → upload room photos / rate card PDF (JPEG/PNG/WebP/PDF, max 10 MB, validated server-side).
- **Spend guard**: each conversation is capped at `daily_token_cap_per_conversation` tokens/day (default 25,000 ≈ a few rupees); beyond it the bot politely hands off to the team.

## 4. How the bot decides what to answer

Incoming message → (voice: Whisper transcription) → intent/language/slot analysis (gpt-5.4-nano) → embedding → cosine similarity against the in-memory KB matrix:

- **≥ 0.90 similarity** → cached KB answer returned verbatim (no completion cost) — *except* pricing/availability/booking messages, which always go through the model, and non-English customers, who get a model reply in their language.
- **0.75–0.90** → top-3 KB entries injected as context into gpt-5.4-mini.
- **< 0.75** → conversational reply + logged to the unanswered queue.

Replies match the customer's language (Urdu → Roman Urdu). Booking intent triggers step-by-step slot collection (dates, party size, type) and automatic lead creation.

---

## 5. Security model (summary)

- All secrets via `.env` (gitignored); `.env.example` documents the shape.
- Every dashboard endpoint requires a JWT; roles enforced server-side. Login rate-limited (5/min) and audit-logged. Webhook + connector API protected by a shared secret with timing-safe comparison; connector binds to localhost only.
- All SQL through SQLAlchemy ORM parameterized statements. Passwords argon2id. Customer PII only in the database and authenticated API responses — never in logs (logs reference internal ids).
- Uploads: MIME whitelist + magic-byte sniffing + size cap, stored under server-generated names outside any webroot.
- Prompt injection: customer text travels only as user-role content; the system prompt forbids revealing instructions, inventing prices, or granting discounts; bookings are confirmed by staff, never by the model.
- `audit_log` records logins (incl. failures), KB changes, takeovers, lead changes, user/media management, deletions.
- Dependency audits at last release: `pip-audit` and `npm audit` — 0 known vulnerabilities.

**Production deployment checklist**: serve the API and dashboard over HTTPS behind a reverse proxy (security headers are already set by the app); bind uvicorn to 127.0.0.1; use the `dbr_app` DB role; encrypt database backups at rest; restrict `WHATSAPP_SESSION_DIR` permissions to the service account. Known accepted trade-offs for the internal tool: refresh tokens are stateless (no server-side revocation list) and stored in `sessionStorage` — revisit both if the dashboard is ever exposed beyond staff.

---

## 6. Migration plan: Baileys → WhatsApp Business Cloud API

Baileys (linked device) is a stopgap for client testing; the official Cloud API is the production target. The system was built so the swap touches **only the connector**:

1. **What stays unchanged**: the backend (webhook payload shape, `/send` contract, media-by-id), the dashboard, the database, and `connector/src/transport.ts` — the provider-agnostic interface (`sendMessage`, `sendMedia`, `onMessageReceived`). No Baileys type leaks outside `connector/src/baileys.ts`.
2. **Get Cloud API access**: Meta Business verification → WhatsApp Business Platform app → register the resort's number (this *deactivates* the Baileys link for that number) → permanent system-user token + webhook verify token.
3. **Write `connector/src/cloudapi.ts`** implementing `WhatsAppTransport`:
   - `onMessageReceived`: expose an HTTPS webhook for Meta (`GET` verify challenge + `POST` messages), map Cloud API message JSON → `InboundMessage` (download media via the media URL endpoint), forward to the backend exactly as today.
   - `sendMessage`/`sendMedia`: `POST https://graph.facebook.com/v<latest>/<phone_id>/messages` (text / image / document / location payloads). Media: upload once, reuse media ids.
   - Respect the 24-hour customer-service window: free-form replies only within 24h of the customer's last message; template messages beyond it (the current bot always replies immediately, so this mainly affects agent follow-ups from the dashboard).
4. **Switch**: change one line in `connector/src/index.ts` (`BaileysTransport` → `CloudApiTransport`), add the Meta tokens to `.env`, delete the Baileys session directory, remove the QR/pairing docs. The human-like delay queue can be retired (no ban risk on the official API).
5. **Cleanup**: drop the `baileys` dependency; keep `provider_message_id` dedup — Cloud API also redelivers webhooks.

---

## 7. Development notes

- Schema changes: `alembic revision --autogenerate -m "..."` → review → `alembic upgrade head`. Never `create_all`, never hand-edit the DB.
- Tests: `cd backend; .\.venv\Scripts\python -m pytest tests -q` · Lint: `.\.venv\Scripts\ruff check app tests scripts`.
- Dashboard build: `cd dashboard; npm run build`. Set `VITE_API_URL` if the API isn't on `127.0.0.1:8000`.
- All DB timestamps are UTC; the UI converts to Asia/Karachi.
