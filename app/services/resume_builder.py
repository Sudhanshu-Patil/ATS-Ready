"""
Resume Builder Service — 1-Page ATS-Optimised DOCX
----------------------------------------------------
Tight spacing, compact fonts, max content density.
ATS rules: single column, no tables for layout, no graphics, standard fonts.
"""
import re
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from docx import Document
from docx.shared import Pt, Inches, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn, nsmap
from docx.oxml import OxmlElement
from docx.opc.constants import RELATIONSHIP_TYPE as RT

from app.config import settings

# ── Palette ───────────────────────────────────────────────────────────────────
DARK   = RGBColor(0x0F, 0x0F, 0x1A)
ACCENT = RGBColor(0x1B, 0x35, 0x7A)
GRAY   = RGBColor(0x55, 0x55, 0x55)
BLACK  = RGBColor(0x1A, 0x1A, 0x1A)
LINK   = RGBColor(0x1B, 0x35, 0x7A)   # same deep blue for hyperlinks


def _add_rule(paragraph, color: str = "1B357A"):
    pPr = paragraph._p.get_or_add_pPr()
    pBdr = OxmlElement("w:pBdr")
    bottom = OxmlElement("w:bottom")
    bottom.set(qn("w:val"), "single")
    bottom.set(qn("w:sz"), "4")
    bottom.set(qn("w:space"), "1")
    bottom.set(qn("w:color"), color)
    pBdr.append(bottom)
    pPr.append(pBdr)


def _sp(paragraph, before: int = 0, after: int = 0):
    pPr = paragraph._p.get_or_add_pPr()
    sp = OxmlElement("w:spacing")
    sp.set(qn("w:before"), str(before))
    sp.set(qn("w:after"),  str(after))
    sp.set(qn("w:line"), "220")
    sp.set(qn("w:lineRule"), "auto")
    pPr.append(sp)


def _add_hyperlink(paragraph, url: str, display: str,
                   size_pt: float = 8.5, color: RGBColor = LINK):
    """
    Insert a clickable hyperlink run into an existing paragraph.
    Works by registering the URL as a relationship on the part, then
    wrapping the run in a w:hyperlink element that references it.
    """
    # Register the URL and get the relationship ID
    part = paragraph.part
    r_id = part.relate_to(url, RT.HYPERLINK, is_external=True)

    # Build w:hyperlink element
    hyperlink = OxmlElement("w:hyperlink")
    hyperlink.set(qn("r:id"), r_id)
    hyperlink.set(qn("w:history"), "1")

    # Build the run inside the hyperlink
    run_elem = OxmlElement("w:r")

    # Run properties
    rPr = OxmlElement("w:rPr")

    style_elem = OxmlElement("w:rStyle")
    style_elem.set(qn("w:val"), "Hyperlink")
    rPr.append(style_elem)

    color_elem = OxmlElement("w:color")
    color_elem.set(qn("w:val"), f"{color[0]:02X}{color[1]:02X}{color[2]:02X}")
    rPr.append(color_elem)

    sz_elem = OxmlElement("w:sz")
    sz_elem.set(qn("w:val"), str(int(size_pt * 2)))
    rPr.append(sz_elem)

    sz_cs = OxmlElement("w:szCs")
    sz_cs.set(qn("w:val"), str(int(size_pt * 2)))
    rPr.append(sz_cs)

    # No underline override — let the Hyperlink style handle it
    run_elem.append(rPr)

    t = OxmlElement("w:t")
    t.text = display
    t.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
    run_elem.append(t)

    hyperlink.append(run_elem)
    paragraph._p.append(hyperlink)


def _add_plain_run(paragraph, text: str, size_pt: float = 8.5,
                   color: RGBColor = GRAY):
    """Add a plain (non-hyperlink) run — used for separators."""
    run = paragraph.add_run(text)
    run.font.name  = "Calibri"
    run.font.size  = Pt(size_pt)
    run.font.color.rgb = color


class ResumeBuilder:

    def __init__(self):
        self.doc: Optional[Document] = None

    def _new_doc(self) -> Document:
        doc = Document()
        for section in doc.sections:
            section.top_margin    = Inches(0.5)
            section.bottom_margin = Inches(0.5)
            section.left_margin   = Inches(0.65)
            section.right_margin  = Inches(0.65)
        style = doc.styles["Normal"]
        style.font.name = "Calibri"
        style.font.size = Pt(9.5)
        style.font.color.rgb = BLACK
        style.paragraph_format.space_before = Pt(0)
        style.paragraph_format.space_after  = Pt(0)
        return doc

    # ── Section header ────────────────────────────────────────────────────────
    def _section(self, title: str):
        p = self.doc.add_paragraph()
        _sp(p, before=80, after=30)
        run = p.add_run(title.upper())
        run.font.name  = "Calibri"
        run.font.size  = Pt(9.5)
        run.font.bold  = True
        run.font.color.rgb = ACCENT
        _add_rule(p)

    # ── Header (name + contact with hyperlinks) ───────────────────────────────
    def _header(self, personal: Dict):
        # Name
        p = self.doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        _sp(p, before=0, after=20)
        run = p.add_run(personal.get("full_name", "Your Name"))
        run.font.name  = "Calibri"
        run.font.size  = Pt(18)
        run.font.bold  = True
        run.font.color.rgb = DARK

        # Contact line — mix of plain text and hyperlinks
        p2 = self.doc.add_paragraph()
        p2.alignment = WD_ALIGN_PARAGRAPH.CENTER
        _sp(p2, before=0, after=50)

        SEP = "  ·  "
        first = True

        def _sep():
            nonlocal first
            if not first:
                _add_plain_run(p2, SEP)
            first = False

        # Email — plain (mailto links render oddly in some viewers)
        if personal.get("email"):
            _sep()
            _add_plain_run(p2, personal["email"])

        # Phone — plain
        if personal.get("phone"):
            _sep()
            _add_plain_run(p2, personal["phone"])

        # Location — plain
        if personal.get("location"):
            _sep()
            _add_plain_run(p2, personal["location"])

        # LinkedIn — hyperlink
        if personal.get("linkedin"):
            url = personal["linkedin"]
            if not url.startswith("http"):
                url = "https://" + url
            _sep()
            _add_hyperlink(p2, url, "LinkedIn")

        # GitHub — hyperlink
        if personal.get("github"):
            url = personal["github"]
            if not url.startswith("http"):
                url = "https://" + url
            _sep()
            _add_hyperlink(p2, url, "GitHub")

        # Portfolio — hyperlink
        if personal.get("portfolio"):
            url = personal["portfolio"]
            if not url.startswith("http"):
                url = "https://" + url
            _sep()
            _add_hyperlink(p2, url, "Portfolio")

    # ── Summary ───────────────────────────────────────────────────────────────
    def _summary(self, text: str):
        self._section("Summary")
        p = self.doc.add_paragraph()
        _sp(p, before=30, after=30)
        run = p.add_run(text)
        run.font.name = "Calibri"
        run.font.size = Pt(9.5)

    # ── Skills ────────────────────────────────────────────────────────────────
    def _skills(self, groups: List[Dict]):
        self._section("Technical Skills")
        for g in groups:
            p = self.doc.add_paragraph()
            _sp(p, before=20, after=16)
            rl = p.add_run(g["category"] + ": ")
            rl.font.bold = True
            rl.font.name = "Calibri"
            rl.font.size = Pt(9.5)
            ri = p.add_run(", ".join(g["items"]))
            ri.font.name = "Calibri"
            ri.font.size = Pt(9.5)

    # ── Experience ────────────────────────────────────────────────────────────
    def _experience(self, experiences: List[Dict]):
        self._section("Work Experience")
        for exp in experiences:
            p = self.doc.add_paragraph()
            _sp(p, before=60, after=10)
            rr = p.add_run(exp.get("role", ""))
            rr.font.bold = True
            rr.font.name = "Calibri"
            rr.font.size = Pt(10)
            rc = p.add_run(f"  —  {exp.get('company','')}")
            rc.font.name  = "Calibri"
            rc.font.size  = Pt(10)
            rc.font.color.rgb = ACCENT

            p2 = self.doc.add_paragraph()
            _sp(p2, before=0, after=20)
            date_str = f"{exp.get('start_date','')} – {exp.get('end_date','Present')}"
            if exp.get("location"):
                date_str += f"  |  {exp['location']}"
            rd = p2.add_run(date_str)
            rd.font.name   = "Calibri"
            rd.font.size   = Pt(8.5)
            rd.font.color.rgb = GRAY
            rd.font.italic = True

            for bullet in exp.get("bullets", []):
                pb = self.doc.add_paragraph(style="List Bullet")
                _sp(pb, before=10, after=10)
                pb.paragraph_format.left_indent = Inches(0.18)
                rb = pb.add_run(bullet)
                rb.font.name = "Calibri"
                rb.font.size = Pt(8.5)

    # ── Projects ──────────────────────────────────────────────────────────────
    def _projects(self, projects: List[Dict]):
        self._section("Projects")
        for proj in projects:
            p = self.doc.add_paragraph()
            _sp(p, before=60, after=10)
            rt = p.add_run(proj.get("title", ""))
            rt.font.bold = True
            rt.font.name = "Calibri"
            rt.font.size = Pt(10)

            # GitHub link inline with title if available
            github = proj.get("github_url")
            if github:
                _add_plain_run(p, "  ", size_pt=10, color=GRAY)
                display = github.replace("https://","").replace("http://","").rstrip("/")
                _add_hyperlink(p, github, f"↗ {display}", size_pt=8.5, color=LINK)

            parts = []
            if proj.get("tech_stack"):
                parts.append(" | ".join(proj["tech_stack"][:5]))
            if proj.get("date_range"):
                parts.append(proj["date_range"])
            if parts:
                p2 = self.doc.add_paragraph()
                _sp(p2, before=0, after=16)
                rtech = p2.add_run("  ·  ".join(parts))
                rtech.font.name  = "Calibri"
                rtech.font.size  = Pt(8.5)
                rtech.font.color.rgb = GRAY
                rtech.font.italic = True

            for bullet in proj.get("bullets", []):
                pb = self.doc.add_paragraph(style="List Bullet")
                _sp(pb, before=10, after=10)
                pb.paragraph_format.left_indent = Inches(0.18)
                rb = pb.add_run(bullet)
                rb.font.name = "Calibri"
                rb.font.size = Pt(8.5)

    # ── Education ─────────────────────────────────────────────────────────────
    def _education(self, education: List[Dict]):
        self._section("Education")
        for edu in education:
            p = self.doc.add_paragraph()
            _sp(p, before=40, after=10)
            rd = p.add_run(f"{edu.get('degree','')} in {edu.get('field','')}")
            rd.font.bold = True
            rd.font.name = "Calibri"
            rd.font.size = Pt(10)
            ri = p.add_run(f"  —  {edu.get('institution','')}")
            ri.font.name  = "Calibri"
            ri.font.size  = Pt(10)
            ri.font.color.rgb = ACCENT

            meta = []
            if edu.get("end_year"):  meta.append(f"Class of {edu['end_year']}")
            if edu.get("gpa"):       meta.append(f"GPA: {edu['gpa']}")
            if edu.get("honors"):    meta.append(edu["honors"])
            if meta:
                p2 = self.doc.add_paragraph()
                _sp(p2, before=0, after=10)
                rm = p2.add_run("  |  ".join(meta))
                rm.font.name  = "Calibri"
                rm.font.size  = Pt(8.5)
                rm.font.color.rgb = GRAY

    # ── Build ─────────────────────────────────────────────────────────────────
    def build(
        self,
        personal: Dict,
        tailored: Dict,
        education: List[Dict],
        filename: Optional[str] = None,
    ) -> Path:
        self.doc = self._new_doc()

        self._header(personal)

        if tailored.get("professional_summary"):
            self._summary(tailored["professional_summary"])

        if tailored.get("skills"):
            self._skills(tailored["skills"])

        if tailored.get("work_experience"):
            self._experience(tailored["work_experience"])

        if tailored.get("projects"):
            self._projects(tailored["projects"])

        if education:
            self._education(education)

        if not filename:
            ts  = datetime.now().strftime("%Y%m%d_%H%M%S")
            uid = str(uuid.uuid4())[:6]
            filename = f"resume_{ts}_{uid}.docx"

        out = settings.OUTPUT_DIR / filename
        self.doc.save(str(out))
        return out


resume_builder = ResumeBuilder()