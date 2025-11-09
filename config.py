# config.py
import os
from dotenv import load_dotenv
load_dotenv()

def must_get(name: str) -> str:
    v = os.getenv(name)
    if not v:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return v

EMAIL_USER = must_get("EMAIL_USER")
EMAIL_PASS = must_get("EMAIL_PASS")
RECIPIENT  = must_get("RECIPIENT")
