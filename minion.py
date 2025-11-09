# config.py
# Loads secrets from a local .env file (not committed to git).
# Works both locally and on GitHub Actions (Actions provides env vars directly).

import os
from dotenv import load_dotenv

# Load .env if present (safe to call even if the file doesn't exist)
load_dotenv()

def must_get(name: str) -> str:
    """Fetch an env var or raise a clear error if missing."""
    val = os.getenv(name)
    if not val:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return val

EMAIL_USER   = must_get("EMAIL_USER")
EMAIL_PASS   = must_get("EMAIL_PASS")
RECIPIENT    = must_get("RECIPIENT")
# minion.py
import smtplib
from email.mime.text import MIMEText
from email.header import Header
from config import EMAIL_USER, EMAIL_PASS, RECIPIENT

def send_email(subject, body):
    msg = MIMEText(body, _subtype="plain", _charset="utf-8")
    msg["Subject"] = Header(subject, "utf-8")
    msg["From"] = EMAIL_USER
    msg["To"] = RECIPIENT

    with smtplib.SMTP("smtp.gmail.com", 587, timeout=30) as server:
        server.ehlo(); server.starttls(); server.ehlo()
        server.login(EMAIL_USER, EMAIL_PASS)  # use your 16-char Gmail app password
        server.send_message(msg)

if __name__ == "__main__":
    send_email("Test from Minion", "Your automation setup is working!")
