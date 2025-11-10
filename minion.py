# minion.py
import os, smtplib, time, re, requests, yaml
from email.header import Header
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.image import MIMEImage
from jinja2 import Environment, FileSystemLoader
from dotenv import load_dotenv

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
def send_email(subject, html):
    msg = MIMEMultipart("related")
    msg["Subject"] = Header(subject, "utf-8")
    msg["From"] = EMAIL_USER
    msg["To"] = RECIPIENT

    alt = MIMEMultipart("alternative")
    msg.attach(alt)
    alt.attach(MIMEText("Open the HTML part to view the digest.", "plain", "utf-8"))

    img_urls = re.findall(r'<img[^>]+src="(https?://[^"]+)"', html)
    cid_map = {}
    for i, url in enumerate(img_urls):
        try:
            r = requests.get(url, timeout=10)
            r.raise_for_status()
            img = MIMEImage(r.content)
            cid = f"img{i}@minion"
            img.add_header("Content-ID", f"<{cid}>")
            msg.attach(img)
            cid_map[url] = f"cid:{cid}"
        except Exception:
            continue

    for url, cid in cid_map.items():
        html = html.replace(f'src="{url}"', f'src="{cid}"')

    alt.attach(MIMEText(html, "html", "utf-8"))

    with smtplib.SMTP("smtp.gmail.com", 587, timeout=30) as server:
        server.ehlo(); server.starttls(); server.ehlo()
        server.login(EMAIL_USER, EMAIL_PASS)
        server.send_message(msg)

# ---------- main ----------
if __name__ == "__main__":
    sections = build_sections()
    html = render_html(sections)
    send_email("Minion · Daily", html)
    print("Minion: email sent.")
