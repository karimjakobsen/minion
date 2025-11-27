# minion.py
import os, smtplib, time, re, yaml
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

def process_latex_images(html_body: str):
    """
    Replace $...$ with <img src="cid:..."> and collect mapping.
    Returns: (new_html, latex_map)
    latex_map: {latex_expression: content_id}
    """
    latex_map = {}
    counter = 1
    
    def repl(match):
        nonlocal counter
        tex = match.group(1).strip()
        cid = f"latex{counter}"
        latex_map[tex] = cid
        counter += 1
        return f'<img src="cid:{cid}" style="vertical-align:middle; max-height:2em;" alt="{tex}">'
    
    # Replace $...$ with image tags
    new_html = re.sub(r'\$(.+?)\$', repl, html_body)
    return new_html, latex_map

# ---------- email with embedded images ----------
def send_email_html(subject: str, html_body: str, latex_map: dict):
    msg = MIMEMultipart("related")
    msg["Subject"] = Header(subject, "utf-8")
    msg["From"] = EMAIL_USER
    msg["To"] = RECIPIENT
    
    alt = MIMEMultipart("alternative")
    msg.attach(alt)
    alt.attach(MIMEText(html_body, "html", "utf-8"))
    
    # Attach rendered LaTeX images
    from providers.tex_to_png import attach_images_to_email
    attach_images_to_email(msg, latex_map)
    
    # Send email
    with smtplib.SMTP("smtp.gmail.com", 587, timeout=30) as server:
        server.ehlo()
        server.starttls()
        server.ehlo()
        server.login(EMAIL_USER, EMAIL_PASS)
        server.send_message(msg)
    
    print(f"✓ Email sent to {RECIPIENT}")

def build_digest():
    """Build the complete HTML digest."""
    sections = build_sections()
    html = render_html(sections)
    return html

# ---------- main ----------
if __name__ == "__main__":
    print("Building digest...")
    html_body = build_digest()
    
    print("Processing LaTeX expressions...")
    html_body, latex_map = process_latex_images(html_body)
    
    print(f"Found {len(latex_map)} LaTeX expressions to render")
    
    print("Sending email...")
    send_email_html("Minion · Daily Digest", html_body, latex_map)
    
    print("Done!")
