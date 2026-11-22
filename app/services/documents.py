"""Downloadable documents rendered on demand: resume PDF, cover letter DOCX/PDF.

The resume .docx is built once at generation time (resume_builder). Its inputs are stored on the
job row (`resume_data`) so a PDF can be rendered later without calling the LLM again.

Resumes are always ONE page: fit_resume() measures the real layout and shrinks fonts a little, then trims the
lowest-value content, until it fits. The DOCX uses the same plan (scale and trimmed content).

shortcut: PDFs use the built-in Helvetica (Latin-1 text). Characters outside it become "?"; bundle a
Unicode TTF and register it with reportlab if non-Latin names/text must be supported.
"""
import copy
import io
import re
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


# Typographic characters the model likes to write that Helvetica (cp1252) cannot draw: each becomes a plain one.
_PLAIN = str.maketrans({
    "‐": "-", "‑": "-", "‒": "-", "−": "-",      # hyphens, non-breaking hyphen, minus
    " ": " ", " ": " ", " ": " ", " ": " ", " ": " ", " ": " ",
    "​": "", "‌": "", "‍": "", "﻿": "", "­": "",
    "→": "->", "⇒": "=>", "≤": "<=", "≥": ">=", "≈": "~", "×": "x",
    "✓": "", "✔": "", "●": "•", "▪": "•", "‣": "•",
})


def _t(value: Any) -> str:
    """Escape for reportlab's mini-markup and keep to what Helvetica can draw."""
    text = escape(str(value or "")).translate(_PLAIN)
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


# ── Resume PDF + one-page fitting ─────────────────────────────────────────────

# Fit is measured on a box no taller than US Letter (and as narrow as A4) with a small safety margin, so the
# same plan stays on ONE page whether printed on A4 or Letter, and in Word (Calibri is narrower and tighter
# than the Helvetica used here, so a layout that fits here fits there).
_FIT_PAGE = (A4[0], 11 * inch)
_SCALES = (1.0, 0.95, 0.9)                         # body text is 9.5pt at 1.0: never below ~8.5pt
# Content trimmed progressively (lowest-value first) when shrinking is not enough.
# proj_n / exp_n: projects / roles kept; proj_b / exp_b: max bullets each; sum: summary sentences.
_LEVELS = (
    {},
    {"proj_b": 2},
    {"proj_b": 2, "exp_b": 4},
    {"proj_b": 1, "exp_b": 4},
    {"proj_b": 1, "proj_n": 2, "exp_b": 3},
    {"proj_b": 1, "proj_n": 1, "exp_b": 3, "sum": 2},
    {"proj_n": 0, "exp_b": 3, "sum": 2},
    {"proj_n": 0, "exp_b": 2, "sum": 2, "skill_items": 10},
    {"proj_n": 0, "exp_b": 2, "exp_n": 3, "sum": 1, "skill_items": 8},
    {"proj_n": 0, "exp_b": 2, "exp_n": 2, "sum": 1, "skill_items": 6},
)


def _resume_story(data: Dict[str, Any], k: float) -> List:
    personal, tailored = data.get("personal") or {}, data.get("tailored") or {}
    name = _style("name", fontName="Helvetica-Bold", fontSize=18 * k, leading=22 * k, alignment=TA_CENTER)
    contact = _style("contact", fontSize=8.5 * k, leading=11 * k, alignment=TA_CENTER, textColor=GRAY)
    section = _style("section", fontName="Helvetica-Bold", fontSize=9.5 * k, leading=12.5 * k, textColor=ACCENT,
                     spaceBefore=8 * k)
    body = _style("body", fontSize=9.5 * k, leading=12.5 * k)
    role = _style("role", fontName="Helvetica-Bold", fontSize=10 * k, leading=13 * k, spaceBefore=4 * k)
    meta = _style("meta", fontName="Helvetica-Oblique", fontSize=8.5 * k, leading=11 * k, textColor=GRAY)
    bullet = _style("bullet", fontSize=9 * k, leading=11.5 * k)

    def head(title: str):
        return [Paragraph(_t(title.upper()), section),
                HRFlowable(width="100%", thickness=0.6, color=ACCENT, spaceAfter=3 * k)]

    def bullets(items):
        items = [b for b in (items or []) if b]
        if not items:
            return []
        return [ListFlowable([ListItem(Paragraph(_t(b), bullet), leftIndent=10) for b in items],
                             bulletType="bullet", bulletFontSize=6 * k, leftIndent=12)]

    story: List = [Paragraph(_t(personal.get("full_name") or "Your Name"), name)]
    contact_bits = [personal.get(c) for c in ("email", "phone", "location", "linkedin", "github", "portfolio")
                    if personal.get(c)]
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
    return story


def _render(data: Dict[str, Any], k: float, page=A4, bottom_extra: float = 0.0):
    """(pdf bytes, number of pages)"""
    buf = io.BytesIO()
    title = f"{(data.get('personal') or {}).get('full_name') or 'Resume'} - Resume"
    doc = SimpleDocTemplate(buf, pagesize=page, title=title, leftMargin=0.65 * inch, rightMargin=0.65 * inch,
                            topMargin=0.55 * inch, bottomMargin=0.55 * inch + bottom_extra)
    doc.build(_resume_story(data, k))
    return buf.getvalue(), doc.page


def _first_sentences(text: str, n: int) -> str:
    parts = [p for p in re.split(r"(?<=[.!?])\s+", (text or "").strip()) if p]
    return " ".join(parts[:n])


def _trimmed(data: Dict[str, Any], level: Dict[str, int]) -> Dict[str, Any]:
    out = copy.deepcopy(data)
    t = out.setdefault("tailored", {})
    if "sum" in level and t.get("professional_summary"):
        t["professional_summary"] = _first_sentences(t["professional_summary"], level["sum"])
    if "skill_items" in level:
        for g in t.get("skills") or []:
            g["items"] = (g.get("items") or [])[:level["skill_items"]]
    if "exp_n" in level:
        t["work_experience"] = (t.get("work_experience") or [])[:level["exp_n"]]
    if "exp_b" in level:
        for e in t.get("work_experience") or []:
            e["bullets"] = (e.get("bullets") or [])[:level["exp_b"]]
    if "proj_n" in level:
        t["projects"] = (t.get("projects") or [])[:level["proj_n"]]
    if "proj_b" in level:
        for p in t.get("projects") or []:
            p["bullets"] = (p.get("bullets") or [])[:level["proj_b"]]
    return out


def fit_resume(data: Dict[str, Any]) -> Dict[str, Any]:
    """Resume data that fits ONE page, plus the font scale: {personal, tailored, education, scale, trim_level}.

    Tries the full content at normal size, then slightly smaller fonts, then trims the lowest-value content
    (extra project bullets, then older-role bullets) and tries again. Content is never reordered; the most
    recent role and the education always stay."""
    for n, level in enumerate(_LEVELS):
        candidate = _trimmed(data, level)
        for k in _SCALES:
            _, pages = _render(candidate, k, page=_FIT_PAGE, bottom_extra=0.15 * inch)
            if pages == 1:
                return {**candidate, "scale": k, "trim_level": n}
    last = _trimmed(data, _LEVELS[-1])                # absurdly long input: keep only the latest role
    last.setdefault("tailored", {})["work_experience"] = (last["tailored"].get("work_experience") or [])[:1]
    return {**last, "scale": _SCALES[-1], "trim_level": len(_LEVELS)}


def resume_pdf(data: Dict[str, Any]) -> bytes:
    """data = {"personal", "tailored", "education"[, "scale"]} as stored by the worker. Rows saved before
    one-page fitting existed have no scale: they are fitted on the fly."""
    fitted = data if data.get("scale") else fit_resume(data)
    return _render(fitted, fitted["scale"])[0]


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
