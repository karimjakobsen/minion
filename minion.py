# minion.py
import os, smtplib, time, re, requests, yaml
from email.header import Header
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.image import MIMEImage
from jinja2 import Environment, FileSystemLoader
from dotenv import load_dotenv
from orchestrator import build_digest
from config import EMAIL_USER, EMAIL_PASS, RECIPIENT

load_dotenv()

# ---------- config ----------
def must_get(name: str) -> str:
    v = os.getenv(name)
    if not v:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return v

EMAIL_USER = must_get("EMAIL_USER")
EMAIL_PASS = must_get("EMAIL_PASS")
RECIPIENT  = must_get("RECIPIENT")

# ---------- render ----------
def build_sections():
    from orchestrator import _run_agent  # uses providers
    with open("topics.yml","r",encoding="utf-8") as f:
        spec = yaml.safe_load(f)
    sections = []
    max_items = int(spec.get("defaults",{}).get("max_items_per_section",5))
    for topic in spec.get("topics",[]):
        heading = topic.get("heading","Untitled")
        combined = []
        for agent in topic.get("agents",[]):
            sec = _run_agent(agent, heading)
            if sec and sec.get("items"):
                combined.extend(sec["items"])
        if combined:
            sections.append({"heading":heading, "items":combined[:max_items]})
    return sections

def render_html(sections):
    env = Environment(loader=FileSystemLoader("templates"))
    tmpl = env.get_template("email.html.j2")
    datestr = time.strftime("%Y-%m-%d")
    # local browser path (handy to open with MathJax)
    view_url = None
    html = tmpl.render(date=datestr, sections=sections, view_url=view_url)
    os.makedirs("data", exist_ok=True)
    web_path = os.path.abspath(os.path.join("data","digest.html"))
    with open(web_path, "w", encoding="utf-8") as f:
        f.write(html)
    print("Browser version saved:", web_path)
    return html

# ---------- email with embedded images ----------
def send_email_html(subject: str, html_body: str):
    msg = MIMEText(html_body, _subtype="html", _charset="utf-8")
    msg["Subject"] = Header(subject, "utf-8")
    msg["From"] = EMAIL_USER
    msg["To"] = RECIPIENT

    # Gmail SMTP example: adjust if you use another provider
    with smtplib.SMTP("smtp.gmail.com", 587, timeout=30) as server:
        server.ehlo(); server.starttls(); server.ehlo()
        server.login(EMAIL_USER, EMAIL_PASS)
        server.send_message(msg)

# ---------- main ----------
if __name__ == "__main__":
    # build digest returns HTML string and writes data/digest.html
    html = build_digest()
    print("Saved browser version and preparing to send email.")
    send_email_html("Minion · Daily Digest", html)
    print("Minion: email sent.")
