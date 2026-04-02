from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, Request, Form, HTTPException, Cookie, UploadFile, File, BackgroundTasks
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
import uvicorn
from database import engine, Base, SessionLocal
from models import Attendee
import qrcode
import os
import uuid
import csv
import io
import base64
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from datetime import datetime, date
import pytz

Base.metadata.create_all(bind=engine)

app = FastAPI(title="AI Impact Conference 2026")
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

QR_DIR = "static/qrcodes"
os.makedirs(QR_DIR, exist_ok=True)

# ── Config ────────────────────────────────────────────────────────────────────
ADMIN_PIN           = os.getenv("ADMIN_PIN", "")
BASE_URL            = os.getenv("BASE_URL", "http://localhost:8000")
GMAIL_CLIENT_ID     = os.getenv("GMAIL_CLIENT_ID", "")
GMAIL_CLIENT_SECRET = os.getenv("GMAIL_CLIENT_SECRET", "")
GMAIL_REFRESH_TOKEN = os.getenv("GMAIL_REFRESH_TOKEN", "")
GMAIL_SENDER        = os.getenv("GMAIL_SENDER", "")
FORCE_DAY           = os.getenv("FORCE_DAY", "")   # "day1" or "day2" for testing only

SESSION_TOKEN = "admin_session"
VALID_TOKEN   = "harvest-admin-authenticated"

UGANDA_TZ = pytz.timezone("Africa/Kampala")


CONFERENCE = {
    "name": "AI Impact Conference 2026",
    "organizer": "Harvest Institute",
    "day1_date": date(2026, 4, 8),
    "day2_date": date(2026, 4, 9),
    "time": "8:00 AM – 4:00 PM",
    "venue": "Worship Harvest Naalya",
}
print(f"DEBUG — Gmail configured: {all([GMAIL_CLIENT_ID, GMAIL_CLIENT_SECRET, GMAIL_REFRESH_TOKEN, GMAIL_SENDER])}")
print(f"DEBUG — FORCE_DAY: '{FORCE_DAY}'")


# ── Helpers ───────────────────────────────────────────────────────────────────

def get_current_day() -> str | None:
    """Returns 'day1', 'day2', or None based on Uganda date or FORCE_DAY override."""
    if FORCE_DAY in ("day1", "day2"):
        return FORCE_DAY
    today = datetime.now(UGANDA_TZ).date()
    if today == CONFERENCE["day1_date"]:
        return "day1"
    elif today == CONFERENCE["day2_date"]:
        return "day2"
    return None


def generate_qr(attendee_id: str):
    qr = qrcode.QRCode(version=1, box_size=8, border=2)
    qr.add_data(attendee_id)
    qr.make(fit=True)
    img = qr.make_image(fill_color="#2D1B8E", back_color="white")
    path = f"{QR_DIR}/{attendee_id}.png"
    img.save(path)


def is_admin(admin_session: str = None) -> bool:
    return admin_session == VALID_TOKEN


async def send_ticket_email(attendee_name: str, attendee_email: str, attendee_id: str):
    if not all([GMAIL_CLIENT_ID, GMAIL_CLIENT_SECRET, GMAIL_REFRESH_TOKEN]):
        print("⚠ Gmail credentials not configured")
        return
    try:
        creds = Credentials(
            token=None,
            refresh_token=GMAIL_REFRESH_TOKEN,
            client_id=GMAIL_CLIENT_ID,
            client_secret=GMAIL_CLIENT_SECRET,
            token_uri="https://oauth2.googleapis.com/token",
        )
        service = build("gmail", "v1", credentials=creds)

        ticket_url = f"{BASE_URL}/ticket/{attendee_id}"
        qr_url     = f"{BASE_URL}/static/qrcodes/{attendee_id}.png"

        html = f"""
        <div style="font-family:Arial,sans-serif;max-width:520px;margin:0 auto;background:#fff;border-radius:16px;overflow:hidden;">
          <div style="background:linear-gradient(135deg,#2D1B8E,#1a0f5c);padding:2rem;text-align:center;">
            <p style="color:rgba(255,255,255,0.5);font-size:0.75rem;letter-spacing:0.15em;text-transform:uppercase;margin:0 0 0.4rem;">Harvest Institute</p>
            <h1 style="color:#fff;font-size:1.5rem;margin:0;font-weight:800;">AI Impact Conference <span style="color:#00BCD4;">2026</span></h1>
          </div>
          <div style="padding:2rem;">
            <p style="color:#374151;margin:0 0 0.75rem;">Hi <strong>{attendee_name}</strong>,</p>
            <p style="color:#6b7280;font-size:0.9rem;margin:0 0 1.5rem;">You're registered for the AI Impact Conference 2026. Here is your ticket.</p>
            <div style="background:#f9fafb;border-radius:12px;padding:1.25rem;margin-bottom:1.5rem;">
              <p style="margin:0 0 0.4rem;font-size:0.85rem;color:#374151;"><strong>📅</strong> Wed 8th & Thu 9th April 2026</p>
              <p style="margin:0 0 0.4rem;font-size:0.85rem;color:#374151;"><strong>🕗</strong> 8:00 AM – 4:00 PM each day</p>
              <p style="margin:0;font-size:0.85rem;color:#374151;"><strong>📍</strong> Worship Harvest Naalya</p>
            </div>
            <div style="text-align:center;margin-bottom:1.5rem;">
              <img src="{qr_url}" width="180" height="180" style="border-radius:8px;" />
              <p style="font-family:monospace;font-size:1.1rem;font-weight:700;color:#2D1B8E;letter-spacing:0.15em;margin:0.5rem 0 0.2rem;">{attendee_id}</p>
              <p style="font-size:0.75rem;color:#9ca3af;margin:0;">Show this QR code at the entrance each day</p>
            </div>
            <a href="{ticket_url}" style="display:block;text-align:center;background:#2D1B8E;color:#fff;padding:0.85rem;border-radius:12px;font-weight:700;text-decoration:none;">View My Ticket →</a>
            <p style="text-align:center;font-size:0.72rem;color:#9ca3af;margin-top:0.75rem;">Bookmark this link to access your QR code anytime</p>
          </div>
        </div>
        """

        msg = MIMEMultipart("alternative")
        msg["Subject"] = "Your Ticket — AI Impact Conference 2026"
        msg["From"]    = f"AI Impact Conference <{GMAIL_SENDER}>"
        msg["To"]      = attendee_email
        msg.attach(MIMEText(html, "html"))

        raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
        service.users().messages().send(userId="me", body={"raw": raw}).execute()
        print(f"✉ Email sent to {attendee_email}")

        db = SessionLocal()
        try:
            a = db.query(Attendee).filter(Attendee.id == attendee_id).first()
            if a:
                a.ticket_sent = True
                db.commit()
        finally:
            db.close()

    except Exception as e:
        print(f"✗ Email failed for {attendee_email}: {e}")


def create_attendee_from_row(name: str, email: str, phone: str = "") -> Attendee | None:
    """Create attendee record + QR. Returns None if email already exists."""
    db = SessionLocal()
    try:
        existing = db.query(Attendee).filter(Attendee.email == email.strip().lower()).first()
        if existing:
            return None
        attendee_id = str(uuid.uuid4())[:8].upper()
        attendee = Attendee(
            id=attendee_id,
            name=name.strip(),
            email=email.strip().lower(),
            phone=phone.strip(),
        )
        db.add(attendee)
        db.commit()
        db.refresh(attendee)
        generate_qr(attendee_id)
        return attendee
    finally:
        db.close()


# ── Auth ──────────────────────────────────────────────────────────────────────

@app.get("/admin/login", response_class=HTMLResponse)
async def login_page(request: Request, error: str = None):
    return templates.TemplateResponse(request, "admin_login.html", {
        "conf": CONFERENCE,
        "error": "Wrong PIN — try again." if error else None
    })


@app.post("/admin/login")
async def login(pin: str = Form(...)):
    if pin == ADMIN_PIN:
        resp = RedirectResponse("/admin", status_code=303)
        resp.set_cookie(SESSION_TOKEN, VALID_TOKEN, httponly=True, max_age=60*60*12)
        return resp
    return RedirectResponse("/admin/login?error=1", status_code=303)


@app.get("/admin/logout")
async def logout():
    resp = RedirectResponse("/admin/login", status_code=303)
    resp.delete_cookie(SESSION_TOKEN)
    return resp


# ── Ticket page (public, per attendee) ───────────────────────────────────────

@app.get("/ticket/{attendee_id}", response_class=HTMLResponse)
async def ticket_page(request: Request, attendee_id: str):
    db = SessionLocal()
    try:
        a = db.query(Attendee).filter(Attendee.id == attendee_id).first()
        if not a:
            raise HTTPException(status_code=404, detail="Ticket not found")
        return templates.TemplateResponse(request, "ticket.html", {
            "attendee": a,
            "qr_url": f"/static/qrcodes/{attendee_id}.png",
            "conf": CONFERENCE,
        })
    finally:
        db.close()


# ── Admin ─────────────────────────────────────────────────────────────────────

@app.get("/admin", response_class=HTMLResponse)
async def admin(
    request: Request,
    admin_session: str = Cookie(default=None)
):
    if not is_admin(admin_session):
        return RedirectResponse("/admin/login", status_code=303)

    db = SessionLocal()
    try:
        attendees  = db.query(Attendee).order_by(Attendee.registered_at.desc()).all()
        total      = len(attendees)
        day1_count = sum(1 for a in attendees if a.checked_in_day1)
        day2_count = sum(1 for a in attendees if a.checked_in_day2)
        tickets_sent = sum(1 for a in attendees if a.ticket_sent)
        current_day = get_current_day()

        return templates.TemplateResponse(request, "admin.html", {
            "attendees": attendees,
            "total": total,
            "day1_count": day1_count,
            "day2_count": day2_count,
            "tickets_sent": tickets_sent,
            "current_day": current_day,
            "conf": CONFERENCE,
            "force_day": FORCE_DAY,
        })
    finally:
        db.close()


@app.post("/admin/scan")
async def scan_checkin(
    attendee_id: str = Form(...),
    admin_session: str = Cookie(default=None)
):
    if not is_admin(admin_session):
        return JSONResponse({"success": False, "message": "Unauthorized"}, status_code=401)

    current_day = get_current_day()
    if not current_day:
        return {"success": False, "message": "Check-in is only active on April 8 and 9. Use FORCE_DAY to test."}

    db = SessionLocal()
    try:
        a = db.query(Attendee).filter(Attendee.id == attendee_id.strip().upper()).first()
        if not a:
            return {"success": False, "message": "Attendee not found"}

        already = a.checked_in_day1 if current_day == "day1" else a.checked_in_day2
        if already:
            return {"success": False, "message": f"{a.name} already checked in for this day"}

        now = datetime.now(UGANDA_TZ)
        if current_day == "day1":
            a.checked_in_day1 = True
            a.checkin_day1_at = now
        else:
            a.checked_in_day2 = True
            a.checkin_day2_at = now
        db.commit()

        return {
            "success": True,
            "message": f"✓ {a.name} checked in!",
            "name": a.name,
            "day": current_day
        }
    finally:
        db.close()


@app.post("/admin/checkin/{attendee_id}")
async def manual_checkin(
    attendee_id: str,
    day: str = "day1",
    admin_session: str = Cookie(default=None)
):
    if not is_admin(admin_session):
        raise HTTPException(status_code=401)

    db = SessionLocal()
    try:
        a = db.query(Attendee).filter(Attendee.id == attendee_id).first()
        if not a:
            raise HTTPException(status_code=404)

        now = datetime.now(UGANDA_TZ)
        if day == "day1":
            a.checked_in_day1 = not a.checked_in_day1
            a.checkin_day1_at = now if a.checked_in_day1 else None
        else:
            a.checked_in_day2 = not a.checked_in_day2
            a.checkin_day2_at = now if a.checked_in_day2 else None
        db.commit()
        return RedirectResponse("/admin", status_code=303)
    finally:
        db.close()


# ── CSV Upload ────────────────────────────────────────────────────────────────

@app.post("/admin/upload-csv")
async def upload_csv(
    request: Request,
    file: UploadFile = File(...),
    admin_session: str = Cookie(default=None),
    background_tasks: BackgroundTasks = None
):
    if not is_admin(admin_session):
        return JSONResponse({"success": False, "message": "Unauthorized"}, status_code=401)

    try:
        contents = await file.read()
        text = contents.decode("utf-8-sig")  # handle BOM from Excel exports
        reader = csv.DictReader(io.StringIO(text))

        # Normalize headers — lowercase, strip spaces
        raw_rows = list(reader)
        if not raw_rows:
            return {"success": False, "message": "CSV is empty"}

        # Try to find name/email/phone columns flexibly
        sample = {k.lower().strip(): v for k, v in raw_rows[0].items()}
        headers = list(sample.keys())

        def find_col(candidates):
            for c in candidates:
                for h in headers:
                    if c in h:
                        return h
            return None

        name_col  = find_col(["name", "full name", "firstname"])
        email_col = find_col(["email", "e-mail", "mail"])
        phone_col = find_col(["phone", "contact", "mobile", "tel"])

        if not name_col or not email_col:
            return {
                "success": False,
                "message": f"Could not find name/email columns. Found: {list({k.lower().strip() for k in raw_rows[0].keys()})}"
            }

        added = 0
        skipped = 0

        for row in raw_rows:
            norm = {k.lower().strip(): v for k, v in row.items()}
            name  = norm.get(name_col, "").strip()
            email = norm.get(email_col, "").strip()
            phone = norm.get(phone_col, "").strip() if phone_col else ""

            if not name or not email:
                skipped += 1
                continue

            attendee = create_attendee_from_row(name, email, phone)
            if attendee:
                await send_ticket_email(attendee.name, attendee.email, attendee.id)
                added += 1
            else:
                skipped += 1

        return {
            "success": True,
            "message": f"✓ {added} tickets sent, {skipped} skipped (already registered or missing data)"
        }

    except Exception as e:
        return {"success": False, "message": f"Error reading CSV: {e}"}


# ── Google Sheet sync (stub — ready to activate) ──────────────────────────────

@app.post("/admin/sync-sheet")
async def sync_sheet(admin_session: str = Cookie(default=None)):
    if not is_admin(admin_session):
        return JSONResponse({"success": False, "message": "Unauthorized"}, status_code=401)
    # TODO: activate when sheet is shared
    # 1. pip install gspread google-auth
    # 2. Set GOOGLE_SHEET_ID and GOOGLE_SERVICE_ACCOUNT_JSON env vars
    # 3. Uncomment the sync logic below
    return {"success": False, "message": "Google Sheet sync not yet configured"}


# ── Health check ──────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    return {"status": "ok"}


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)


# ── Resend ticket (admin action) ──────────────────────────────────────────────

@app.post("/admin/resend-ticket")
async def resend_ticket_endpoint(
    attendee_id: str = Form(...),
    admin_session: str = Cookie(default=None),
    background_tasks: BackgroundTasks = None
):
    if not is_admin(admin_session):
        return JSONResponse({"success": False, "message": "Unauthorized"}, status_code=401)
    db = SessionLocal()
    try:
        a = db.query(Attendee).filter(Attendee.id == attendee_id).first()
        if not a:
            return {"success": False, "message": "Attendee not found"}
        background_tasks.add_task(send_ticket_email, a.name, a.email, a.id)
        return {"success": True, "message": f"Ticket resent to {a.email}"}
    finally:
        db.close()