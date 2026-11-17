"""Downloadable documents rendered on demand: resume PDF, cover letter DOCX/PDF.

The resume .docx is built once at generation time (resume_builder). Its inputs are stored on the
job row (`resume_data`) so a PDF can be rendered later without calling the LLM again.

shortcut: PDFs use the built-in Helvetica (Latin-1 text). Characters outside it become "?"; bundle a
Unicode TTF and register it with reportlab if non-Latin names/text must be supported.
"""
import io
from typing import Any, Dict, List
from xml.sax.saxutils import escape

from docx import Document
from docx.shared import Inches, Pt
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import HRFlowable, ListFlowable, ListItem, Paragraph, SimpleDocTemplate, Spacer

ACCENT = colors.HexColor("#1B357A")
GRAY = colors.HexColor("#555555")


def _t(value: Any) -> str:
    """Escape for reportlab's mini-markup and keep to what Helvetica can draw."""
    text = escape(str(value or ""))
    return text.encode("cp1252", "replace").decode("cp1252")


def _style(name: str, **kw) -> ParagraphStyle:
    return ParagraphStyle(name, fontName=kw.pop("fontName", "Helvetica"), fontSize=kw.pop("fontSize", 9.5),
                          leading=kw.pop("leading", 12.5), **kw)


def _pdf(story: List, title: str, margins=(0.65, 0.55)) -> bytes:
    buf = io.BytesIO()
    side, vert = margins
    SimpleDocTemplate(buf, pagesize=A4, title=title, leftMargin=side * inch, rightMargin=side * inch,
                      topMargin=vert * inch, bottomMargin=vert * inch).build(story)
    return buf.getvalue()


# ── Resume PDF ───────────────────────────────────────────────────────────────

def resume_pdf(data: Dict[str, Any]) -> bytes:
    """data = {"personal": {...}, "tailored": {...}, "education": [...]} as stored by the worker."""
    personal, tailored = data.get("personal") or {}, data.get("tailored") or {}
    name = _style("name", fontName="Helvetica-Bold", fontSize=18, leading=22, alignment=TA_CENTER)
    contact = _style("contact", fontSize=8.5, leading=11, alignment=TA_CENTER, textColor=GRAY)
    section = _style("section", fontName="Helvetica-Bold", fontSize=9.5, textColor=ACCENT, spaceBefore=8)
    body = _style("body")
    role = _style("role", fontName="Helvetica-Bold", fontSize=10, leading=13, spaceBefore=4)
    meta = _style("meta", fontName="Helvetica-Oblique", fontSize=8.5, leading=11, textColor=GRAY)
    bullet = _style("bullet", fontSize=9, leading=11.5)

    def head(title: str):
        return [Paragraph(_t(title.upper()), section),
                HRFlowable(width="100%", thickness=0.6, color=ACCENT, spaceAfter=3)]

    def bullets(items):
        items = [b for b in (items or []) if b]
        if not items:
            return []
        return [ListFlowable([ListItem(Paragraph(_t(b), bullet), leftIndent=10) for b in items],
                             bulletType="bullet", bulletFontSize=6, leftIndent=12)]

    story: List = [Paragraph(_t(personal.get("full_name") or "Your Name"), name)]
    contact_bits = [personal.get(k) for k in ("email", "phone", "location", "linkedin", "github", "portfolio")
                    if personal.get(k)]
    if contact_bits:
        story.append(Paragraph("  |  ".join(_t(b) for b in contact_bits), contact))

    if tailored.get("professional_summary"):
        story += head("Summary") + [Paragraph(_t(tailored["professional_summary"]), body)]

    if tailored.get("skills"):
        story += head("Technical Skills")
        for g in tailored["skills"]:
            story.append(Paragraph(f"<b>{_t(g.get('category'))}:</b> {_t(', '.join(g.get('items') or []))}", body))

    if tailored.get("work_experience"):
        story += head("Work Experience")
        for e in tailored["work_experience"]:
            story.append(Paragraph(f"{_t(e.get('role'))} - <font color='#1B357A'>{_t(e.get('company'))}</font>", role))
            dates = f"{e.get('start_date') or ''} - {e.get('end_date') or 'Present'}"
            if e.get("location"):
                dates += f"  |  {e['location']}"
            story.append(Paragraph(_t(dates), meta))
            story += bullets(e.get("bullets"))

    if tailored.get("projects"):
        story += head("Projects")
        for p in tailored["projects"]:
            story.append(Paragraph(_t(p.get("title")), role))
            sub = "  |  ".join(x for x in [" | ".join((p.get("tech_stack") or [])[:5]), p.get("date_range") or ""] if x)
            if sub:
                story.append(Paragraph(_t(sub), meta))
            story += bullets(p.get("bullets"))

    if data.get("education"):
        story += head("Education")
        for ed in data["education"]:
            line = " in ".join(x for x in [ed.get("degree"), ed.get("field")] if x)
            story.append(Paragraph(f"{_t(line)} - <font color='#1B357A'>{_t(ed.get('institution'))}</font>", role))
            extra = [f"Class of {ed['end_year']}" if ed.get("end_year") else "",
                     f"GPA: {ed['gpa']}" if ed.get("gpa") else "", ed.get("honors") or ""]
            if any(extra):
                story.append(Paragraph(_t("  |  ".join(x for x in extra if x)), meta))

    return _pdf(story, f"{personal.get('full_name') or 'Resume'} - Resume")


# ── Cover letter ─────────────────────────────────────────────────────────────

def _paragraphs(body: str) -> List[str]:
    return [p.strip() for p in (body or "").replace("\r\n", "\n").split("\n\n") if p.strip()]


def cover_letter_pdf(subject: str, body: str) -> bytes:
    sub = _style("sub", fontName="Helvetica-Bold", fontSize=11, leading=15, spaceAfter=10)
    para = _style("para", fontSize=10.5, leading=15, spaceAfter=9)
    story: List = [Paragraph(_t(subject), sub)] if subject else []
    for p in _paragraphs(body):
        story.append(Paragraph(_t(p).replace("\n", "<br/>"), para))
    story.append(Spacer(1, 4))
    return _pdf(story, subject or "Cover letter", margins=(1.0, 0.9))


def cover_letter_docx(subject: str, body: str) -> bytes:
    doc = Document()
    for s in doc.sections:
        s.top_margin = s.bottom_margin = Inches(1)
        s.left_margin = s.right_margin = Inches(1)
    style = doc.styles["Normal"]
    style.font.name, style.font.size = "Calibri", Pt(11)
    if subject:
        p = doc.add_paragraph()
        p.add_run(subject).bold = True
        p.paragraph_format.space_after = Pt(10)
    for text in _paragraphs(body):
        p = doc.add_paragraph()
        for i, line in enumerate(text.split("\n")):
            if i:
                p.add_run().add_break()
            p.add_run(line)
        p.paragraph_format.space_after = Pt(8)
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()
