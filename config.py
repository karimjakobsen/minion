# config.py
import os
from dotenv import load_dotenv
load_dotenv()

def must_get(name: str) -> str:
    val = os.getenv(name)
    if not val:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return val

EMAIL_USER = must_get("EMAIL_USER")
EMAIL_PASS = must_get("EMAIL_PASS")
RECIPIENT  = must_get("RECIPIENT")
