

def test_pdf_text_keeps_hyphens_the_model_writes():
    from app.services.documents import _t
    assert _t("multi\u2011tenant per\u2011tenant sub\u2011second") == "multi-tenant per-tenant sub-second"
    assert "?" not in _t("a\u2010b \u2192 c \u2265 d")
