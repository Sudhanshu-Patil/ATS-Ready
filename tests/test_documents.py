

def test_pdf_text_keeps_hyphens_the_model_writes():
    from app.services.documents import _t
    assert _t("multi\u2011tenant per\u2011tenant sub\u2011second") == "multi-tenant per-tenant sub-second"
    assert "?" not in _t("a\u2010b \u2192 c \u2265 d")


def test_pdf_has_real_links_with_short_labels():
    from app.services.documents import resume_pdf
    data = {"personal": {"full_name": "A B", "email": "a@b.co", "linkedin": "linkedin.com/in/ab", "github": "https://github.com/ab"},
            "tailored": {"projects": [{"title": "Proj", "github_url": "https://github.com/ab/p", "bullets": ["Did a thing."]}]},
            "education": []}
    pdf = resume_pdf(data)
    assert pdf.count(b"/URI") >= 4                       # email, LinkedIn, GitHub, project GitHub
    assert b"https://linkedin.com/in/ab" in pdf or b"linkedin.com/in/ab" in pdf
