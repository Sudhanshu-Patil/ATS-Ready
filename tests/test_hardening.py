"""Security headers, body-size limit, health endpoints, no static /outputs."""


async def test_security_headers_on_every_response(client):
    r = await client.get("/health")
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["x-frame-options"] == "DENY"
    assert "frame-ancestors 'none'" in r.headers["content-security-policy"]
    assert "max-age=" in r.headers["strict-transport-security"]


async def test_oversized_body_rejected_by_content_length(client):
    r = await client.post("/api/auth/login", content=b"x" * (7 * 1024 * 1024),
                          headers={"content-type": "application/x-www-form-urlencoded"})
    assert r.status_code == 413


async def test_oversized_chunked_body_rejected(client):
    async def chunks():
        for _ in range(7):
            yield b"x" * (1024 * 1024)
    r = await client.post("/api/auth/login", content=chunks(),
                          headers={"content-type": "application/x-www-form-urlencoded"})
    assert r.status_code == 413


async def test_ready_reports_status_without_internals(client):
    r = await client.get("/health/ready")
    assert r.status_code == 200
    assert r.json()["database"] == "ok"
    assert set(r.json()) <= {"status", "database", "redis"}


async def test_detailed_health_and_static_outputs_are_gone(client):
    for path in ("/api/health/detailed", "/outputs/anything.docx"):
        r = await client.get(path)
        assert r.status_code == 404 and "json" in r.headers["content-type"]
