# providers/pdf_math.py
import os
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4

def generate_math_pdf(problems, pdf_path):
    """
    problems: list of dicts with "problem" and "tip".
    pdf_path: output path, e.g. data/math/today.pdf
    """

    os.makedirs(os.path.dirname(pdf_path), exist_ok=True)

    c = canvas.Canvas(pdf_path, pagesize=A4)
    width, height = A4

    y = height - 80
    c.setFont("Helvetica", 12)

    for p in problems:
        text = p["problem"]
        tip = p["tip"]

        # Problem
        c.drawString(50, y, text)
        y -= 20

        # Tip
        c.setFont("Helvetica-Oblique", 10)
        c.drawString(60, y, f"Tip: {tip}")
        c.setFont("Helvetica", 12)
        y -= 30

        # Avoid overflow
        if y < 80:
            c.showPage()
            c.setFont("Helvetica", 12)
            y = height - 80
    c.setTitle("Daily CS problem")
    c.save()
