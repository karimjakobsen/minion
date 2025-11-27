# providers/tex_to_png.py
import re
import requests
from email.mime.image import MIMEImage
from urllib.parse import quote

CODECOGS_URL = "https://latex.codecogs.com/png.latex?"

def extract_latex(expr: str):
    """
    Find all $...$ expressions in a string.
    Returns list of tex strings without the dollar signs.
    """
    return re.findall(r'\$(.+?)\$', expr)

def render_latex_to_png(tex: str):
    """
    Fetch PNG bytes from CodeCogs.
    Uses moderate DPI and size for better quality without being too large.
    """
    # Reduced DPI and using \normalsize instead of \large for smaller text
    latex_with_options = r"\dpi{120} \normalsize \color{Magenta} " + tex
    url = CODECOGS_URL + quote(latex_with_options)
    
    try:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        return resp.content
    except Exception as e:
        print(f"ERROR rendering LaTeX '{tex}': {e}")
        # Return a fallback small transparent PNG
        return b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82'

def attach_images_to_email(msg, mapping):
    """
    mapping: {latex_string: content_id}
    Attaches rendered PNGs to msg.
    """
    for tex, cid in mapping.items():
        print(f"  Rendering: ${tex}$ -> cid:{cid}")
        png_bytes = render_latex_to_png(tex)
        img = MIMEImage(png_bytes, _subtype="png")
        img.add_header("Content-ID", f"<{cid}>")
        img.add_header("Content-Disposition", "inline", filename=f"{cid}.png")
        msg.attach(img)
