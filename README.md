# AI Impact Conference 2026 — Registration System

A clean, Luma-inspired registration and check-in system for the Harvest Institute AI Impact Conference 2026.

## Features
- Registration page (name, email, day selection)
- Unique QR code generated per attendee
- Admin dashboard with independent Day 1 / Day 2 check-in
- Quick check-in by attendee ID
- Live search/filter on admin dashboard
- Duplicate email prevention

## Pages
| Route | Description |
|-------|-------------|
| `/` | Public registration page |
| `/success/{id}` | Confirmation page with QR code |
| `/admin` | Admin check-in dashboard |
| `/admin?day=day2` | Switch to Day 2 check-in |

## Run Locally

```bash
pip install -r requirements.txt
python main.py
```

Then visit: http://localhost:8000

## Deploy to Render

1. Push this folder to a GitHub repo
2. Go to render.com → New Web Service
3. Connect your GitHub repo
4. Build command: `pip install -r requirements.txt`
5. Start command: `uvicorn main:app --host 0.0.0.0 --port $PORT`
6. Deploy!

> **Note:** SQLite works fine for this event scale. If you want data to persist across Render redeploys, upgrade to PostgreSQL on Neon and set the `DATABASE_URL` environment variable.

## Upgrading to PostgreSQL (Neon)

1. Create a database on neon.tech
2. In Render, set environment variable:
   ```
   DATABASE_URL=postgresql://user:password@host/dbname
   ```
3. Remove the `connect_args` SQLite workaround in `database.py` — it's already handled automatically.
