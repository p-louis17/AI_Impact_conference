from fastapi import FastAPI, Request, Form, HTTPException, Cookie
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
import uvicorn
from database import engine, Base, SessionLocal
from models import Attendee
import qrcode
import os
import uuid
import aiosmtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.image import MIMEImage
from dotenv import load_dotenv
load_dotenv()

Base.metadata.create_all(bind=engine)

app = FastAPI(title="AI Impact Conference 2026")

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

QR_DIR = "static/qrcodes"
os.makedirs(QR_DIR, exist_ok=True)

CONFERENCE = {
    "name": "AI Impact Conference 2026",
    "organizer": "Harvest Institute",
    "day1": "Wednesday, April 8th 2026",
    "day2": "Thursday, April 9th 2026",
    "time": "8:00 AM – 4:00 PM",
    "venue": "Worship Harvest Naalya",
}

# ── Config from environment ──────────────────────────────────────────────────
ADMIN_PIN      = os.getenv("ADMIN_PIN", "")
GMAIL_USER     = os.getenv("GMAIL_USER", "")
GMAIL_PASSWORD = os.getenv("GMAIL_APP_PASSWORD", "")
BASE_URL       = os.getenv("BASE_URL", "")
SESSION_TOKEN  = "admin_session"
VALID_TOKEN    = "harvest-admin-authenticated"
# print(f"DEBUG EMAIL CONFIG — user='{GMAIL_USER}' pass_set={bool(GMAIL_PASSWORD)}")


# ── Helpers ──────────────────────────────────────────────────────────────────

def generate_qr(attendee_id: str):
    qr = qrcode.QRCode(version=1, box_size=8, border=2)
    qr.add_data(attendee_id)
    qr.make(fit=True)
    img = qr.make_image(fill_color="#2D1B8E", back_color="white")
    path = f"{QR_DIR}/{attendee_id}.png"
    img.save(path)
    return path


def is_admin_authenticated(admin_session: str = None) -> bool:
    return admin_session == VALID_TOKEN


async def send_confirmation_email(attendee_name: str, attendee_email: str,
                                   attendee_id: str, day1: bool, day2: bool):
    if not GMAIL_USER or not GMAIL_PASSWORD:
        print("⚠ Email not configured — skipping email send")
        return
    try:
        if day1 and day2:
            days_text = "Day 1 (Wed, April 8) and Day 2 (Thu, April 9)"
        elif day1:
            days_text = "Day 1 — Wednesday, April 8"
        else:
            days_text = "Day 2 — Thursday, April 9"

        ticket_url = f"{BASE_URL}/ticket/{attendee_id}"

        msg = MIMEMultipart("related")
        msg["Subject"] = "Your Ticket — AI Impact Conference 2026"
        msg["From"]    = f"Harvest Institute <{GMAIL_USER}>"
        msg["To"]      = attendee_email

        html = f"""
        <div style="font-family:'DM Sans',Arial,sans-serif;max-width:520px;margin:0 auto;background:#fff;border-radius:16px;overflow:hidden;box-shadow:0 4px 24px rgba(45,27,142,0.10);">
          <div style="background:linear-gradient(135deg,#2D1B8E,#1a0f5c);padding:2rem 2rem 2.5rem;text-align:center;">
            <p style="color:rgba(255,255,255,0.55);font-size:0.8rem;letter-spacing:0.15em;text-transform:uppercase;margin:0 0 0.5rem;">Harvest Institute</p>
            <h1 style="color:#fff;font-size:1.6rem;margin:0;font-weight:800;">AI Impact Conference <span style="color:#00BCD4;">2026</span></h1>
          </div>
          <div style="padding:2rem;">
            <p style="color:#374151;font-size:1rem;margin:0 0 1rem;">Hi <strong>{attendee_name}</strong>,</p>
            <p style="color:#6b7280;font-size:0.9rem;margin:0 0 1.5rem;">You're registered! Here are your details:</p>
            <div style="background:#f9fafb;border-radius:12px;padding:1.25rem;margin-bottom:1.5rem;">
              <p style="margin:0 0 0.5rem;font-size:0.85rem;color:#374151;"><strong>📅 Days:</strong> {days_text}</p>
              <p style="margin:0 0 0.5rem;font-size:0.85rem;color:#374151;"><strong>🕗 Time:</strong> 8:00 AM – 4:00 PM</p>
              <p style="margin:0;font-size:0.85rem;color:#374151;"><strong>📍 Venue:</strong> Worship Harvest Naalya</p>
            </div>
            <div style="text-align:center;margin-bottom:1.5rem;">
              <img src="cid:qrcode" width="180" height="180" style="border-radius:8px;" />
              <p style="font-family:monospace;font-size:1.1rem;font-weight:700;color:#2D1B8E;letter-spacing:0.15em;margin:0.5rem 0 0.25rem;">{attendee_id}</p>
              <p style="font-size:0.78rem;color:#9ca3af;margin:0;">Show this QR code at the door each day</p>
            </div>
            <a href="{ticket_url}" style="display:block;text-align:center;background:#2D1B8E;color:#fff;padding:0.85rem;border-radius:12px;font-weight:700;text-decoration:none;font-size:0.95rem;">View My Ticket →</a>
            <p style="text-align:center;font-size:0.75rem;color:#9ca3af;margin-top:0.75rem;">Keep this link — you can access your QR code anytime</p>
          </div>
        </div>
        """

        msg.attach(MIMEText(html, "html"))

        qr_path = f"{QR_DIR}/{attendee_id}.png"
        if os.path.exists(qr_path):
            with open(qr_path, "rb") as f:
                img_data = MIMEImage(f.read())
                img_data.add_header("Content-ID", "<qrcode>")
                img_data.add_header("Content-Disposition", "inline")
                msg.attach(img_data)

        await aiosmtplib.send(
            msg,
            hostname="smtp.gmail.com",
            port=587,
            username=GMAIL_USER,
            password=GMAIL_PASSWORD,
            start_tls=True,
        )
        print(f"✉ Email sent to {attendee_email}")

    except Exception as e:
        print(f"✗ Email failed for {attendee_email}: {e}")


# ── Admin Auth ────────────────────────────────────────────────────────────────

@app.get("/admin/login", response_class=HTMLResponse)
async def admin_login_page(request: Request, error: str = None):
    return templates.TemplateResponse(request, "admin_login.html", {
        "conf": CONFERENCE,
        "error": "Wrong PIN. Try again." if error else None
    })


@app.post("/admin/login")
async def admin_login(pin: str = Form(...)):
    if pin == ADMIN_PIN:
        response = RedirectResponse("/admin", status_code=303)
        response.set_cookie(
            key=SESSION_TOKEN,
            value=VALID_TOKEN,
            httponly=True,
            max_age=60 * 60 * 12  # 12 hours
        )
        return response
    return RedirectResponse("/admin/login?error=1", status_code=303)


@app.get("/admin/logout")
async def admin_logout():
    response = RedirectResponse("/admin/login", status_code=303)
    response.delete_cookie(SESSION_TOKEN)
    return response


# ── Registration ──────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def register_page(request: Request):
    return templates.TemplateResponse(request, "register.html", {
        "conf": CONFERENCE,
        "error": None
    })


@app.post("/register", response_class=HTMLResponse)
async def register(
    request: Request,
    name: str = Form(...),
    email: str = Form(...),
    days: list[str] = Form(...)
):
    db = SessionLocal()
    try:
        existing = db.query(Attendee).filter(Attendee.email == email).first()
        if existing:
            return templates.TemplateResponse(request, "register.html", {
                "conf": CONFERENCE,
                "error": f"This email is already registered. <a href='/ticket/{existing.id}' style='color:#2D1B8E;font-weight:600;'>View your ticket →</a>"
            })

        attendee_id = str(uuid.uuid4())[:8].upper()
        day1 = "day1" in days
        day2 = "day2" in days

        attendee = Attendee(
            id=attendee_id,
            name=name,
            email=email,
            day1=day1,
            day2=day2,
        )
        db.add(attendee)
        db.commit()

        generate_qr(attendee_id)

        # Fire-and-forget async email — non-blocking
        import asyncio
        asyncio.create_task(send_confirmation_email(name, email, attendee_id, day1, day2))

        return RedirectResponse(f"/success/{attendee_id}", status_code=303)
    finally:
        db.close()


@app.get("/success/{attendee_id}", response_class=HTMLResponse)
async def success_page(request: Request, attendee_id: str):
    db = SessionLocal()
    try:
        attendee = db.query(Attendee).filter(Attendee.id == attendee_id).first()
        if not attendee:
            raise HTTPException(status_code=404, detail="Attendee not found")
        return templates.TemplateResponse(request, "success.html", {
            "conf": CONFERENCE,
            "attendee": attendee,
            "qr_url": f"/static/qrcodes/{attendee_id}.png",
            "ticket_url": f"{BASE_URL}/ticket/{attendee_id}"
        })
    finally:
        db.close()


@app.get("/ticket/{attendee_id}", response_class=HTMLResponse)
async def ticket_page(request: Request, attendee_id: str):
    db = SessionLocal()
    try:
        attendee = db.query(Attendee).filter(Attendee.id == attendee_id).first()
        if not attendee:
            raise HTTPException(status_code=404, detail="Ticket not found")
        return templates.TemplateResponse(request, "ticket.html", {
            "conf": CONFERENCE,
            "attendee": attendee,
            "qr_url": f"/static/qrcodes/{attendee_id}.png",
        })
    finally:
        db.close()


# ── Admin Dashboard ───────────────────────────────────────────────────────────

@app.get("/admin", response_class=HTMLResponse)
async def admin_dashboard(
    request: Request,
    day: str = "day1",
    admin_session: str = Cookie(default=None)
):
    if not is_admin_authenticated(admin_session):
        return RedirectResponse("/admin/login", status_code=303)

    db = SessionLocal()
    try:
        if day == "day1":
            attendees = db.query(Attendee).filter(Attendee.day1 == True).all()
        else:
            attendees = db.query(Attendee).filter(Attendee.day2 == True).all()

        checked_in = sum(1 for a in attendees if (
            a.checked_in_day1 if day == "day1" else a.checked_in_day2
        ))

        return templates.TemplateResponse(request, "admin.html", {
            "conf": CONFERENCE,
            "attendees": attendees,
            "active_day": day,
            "total": len(attendees),
            "checked_in": checked_in,
        })
    finally:
        db.close()


@app.post("/admin/checkin/{attendee_id}")
async def checkin(
    attendee_id: str,
    day: str = "day1",
    admin_session: str = Cookie(default=None)
):
    if not is_admin_authenticated(admin_session):
        raise HTTPException(status_code=401, detail="Unauthorized")

    db = SessionLocal()
    try:
        attendee = db.query(Attendee).filter(Attendee.id == attendee_id).first()
        if not attendee:
            raise HTTPException(status_code=404, detail="Attendee not found")

        if day == "day1":
            attendee.checked_in_day1 = not attendee.checked_in_day1
        else:
            attendee.checked_in_day2 = not attendee.checked_in_day2

        db.commit()
        return RedirectResponse(f"/admin?day={day}", status_code=303)
    finally:
        db.close()


@app.post("/admin/scan")
async def scan_checkin(
    request: Request,
    attendee_id: str = Form(...),
    day: str = Form(...),
    admin_session: str = Cookie(default=None)
):
    if not is_admin_authenticated(admin_session):
        return JSONResponse({"success": False, "message": "Unauthorized"}, status_code=401)

    db = SessionLocal()
    try:
        attendee = db.query(Attendee).filter(Attendee.id == attendee_id.upper()).first()
        if not attendee:
            return {"success": False, "message": "Attendee not found"}

        registered = attendee.day1 if day == "day1" else attendee.day2
        if not registered:
            return {"success": False, "message": f"{attendee.name} is not registered for this day"}

        if day == "day1":
            if attendee.checked_in_day1:
                return {"success": False, "message": f"{attendee.name} already checked in for Day 1"}
            attendee.checked_in_day1 = True
        else:
            if attendee.checked_in_day2:
                return {"success": False, "message": f"{attendee.name} already checked in for Day 2"}
            attendee.checked_in_day2 = True

        db.commit()
        return {"success": True, "message": f"✓ {attendee.name} checked in!", "name": attendee.name}
    finally:
        db.close()


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
