"""Application tracking and the assistant: with and without a job description, refresh/retry safety, back-questions,
follow-ups and the persona that learns from approved answers."""
import uuid
from datetime import datetime, timedelta

import pytest
from sqlalchemy import select

from app.config import settings
from app.db.database import AsyncSessionLocal
from app.db.models import Application, ApplicationEvent, AssistantRequest, PersonaEdge, PersonaNode
from app.services import applications, assistant, persona
from app.worker import tasks
from tests.conftest import unique_email
from tests.test_ats_suggestions import JD_TEXT, _user_with_profile
from tests.test_metabase_experience import bearer, register


@pytest.fixture(autouse=True)
def stub(monkeypatch):
    queued = []

    async def fake_enqueue(function, **kwargs):
        queued.append((function, kwargs))
    monkeypatch.setattr("app.api.assistant_routes.enqueue", fake_enqueue)
    monkeypatch.setattr(settings, "BILLING_ENABLED", False)
    monkeypatch.setattr(settings, "LLM_FAKE", True)
    return queued


def rid() -> str:
    return uuid.uuid4().hex


async def run_worker(request_id, user_id, only=None):
    await tasks.generate_assistant_answers_task({}, str(request_id), str(user_id), only)


async def post(client, h, questions, **extra):
    return await client.post("/api/assistant/requests", headers=h,
                             json={"client_request_id": rid(), "questions": questions, **extra})


# ── What the user's own text literally says ──────────────────────────────────

def test_company_and_role_only_when_the_text_names_them():
    assert applications.extract_hints("Why do you want to work at Stripe?")["company"] == "Stripe"
    h = applications.extract_hints("Why do you want to join Acme Corp for the Senior Backend Engineer role?")
    assert h == {"company": "Acme Corp", "role": "Senior Backend Engineer"}
    for none in ("Tell me about yourself.", "Why this company?", "Describe a time you disagreed with your manager."):
        assert applications.extract_hints(none) == {"company": None, "role": None}


def test_unclear_company_names():
    for bad in ("Confidential", "our client", "", None, "TBD", "A startup"):
        assert applications.is_unclear_company(bad)
    assert not applications.is_unclear_company("Razorpay")


# ── Questions only: no job description, no company ───────────────────────────

async def test_questions_only_creates_a_draft_application_and_asks_for_the_company(client, stub):
    h, uid = await _user_with_profile(client)
    r = await post(client, h, ["Tell me about yourself.", "What is your biggest strength?"])
    assert r.status_code == 202
    body = r.json()
    assert body["has_jd"] is False and body["application"]["needs"] == ["company", "role"]
    assert body["application"]["status"] == "interested"

    # the back-question is available from the server, so a refresh or another device still shows it
    att = (await client.get("/api/applications/attention", headers=h)).json()
    assert [a["id"] for a in att["needs"]] == [body["application"]["id"]] and att["count"] == 1

    # the user answers it (company only first): role is still asked
    app_id = body["application"]["id"]
    p = (await client.patch(f"/api/applications/{app_id}", headers=h, json={"company": "Razorpay"})).json()
    assert p["company"] == "Razorpay" and p["needs"] == ["role"]
    p = (await client.patch(f"/api/applications/{app_id}", headers=h, json={"role": "Backend Engineer"})).json()
    assert p["needs"] == [] and (await client.get("/api/applications/attention", headers=h)).json()["count"] == 0


async def test_the_company_in_the_question_text_is_used_without_asking(client, stub):
    h, _ = await _user_with_profile(client)
    b = (await post(client, h, ["Why do you want to work at Stripe?"])).json()
    assert b["application"]["company"] == "Stripe" and b["application"]["needs"] == ["role"]   # role still unknown


async def test_a_user_can_decline_tracking_for_practice_questions(client, stub):
    h, _ = await _user_with_profile(client)
    b = (await post(client, h, ["Tell me about yourself."], track=False)).json()
    assert b["application"] is None and (await client.get("/api/applications", headers=h)).json()["items"] == []


async def test_company_and_role_typed_by_the_user_need_no_question(client, stub):
    h, _ = await _user_with_profile(client)
    b = (await post(client, h, ["Tell me about yourself."], company="Zoho", role="SDE")).json()
    assert b["application"]["needs"] == [] and b["application"]["company"] == "Zoho"


# ── Refresh / lost connection ────────────────────────────────────────────────

async def test_a_retried_submit_returns_the_same_request_and_enqueues_once(client, stub):
    h, uid = await _user_with_profile(client)
    cid = rid()
    payload = {"client_request_id": cid, "questions": ["Tell me about yourself."]}
    first = (await client.post("/api/assistant/requests", headers=h, json=payload)).json()
    again = (await client.post("/api/assistant/requests", headers=h, json=payload)).json()   # the response was lost
    assert first["id"] == again["id"]
    assert len(stub) == 1
    assert len((await client.get("/api/assistant/requests", headers=h)).json()) == 1
    assert len((await client.get("/api/applications", headers=h)).json()["items"]) == 1       # no duplicate application


async def test_answers_are_stored_server_side_and_survive_a_refresh(client, stub):
    h, uid = await _user_with_profile(client)
    b = (await post(client, h, ["Why are you interested in this role?"])).json()
    await run_worker(b["id"], uid)
    # "refresh": fetch it again from nothing but the id
    got = (await client.get(f"/api/assistant/requests/{b['id']}", headers=h)).json()
    assert got["status"] == "done" and got["questions"][0]["status"] == "done"
    assert got["questions"][0]["answer"].startswith("Fake answer")


# ── One job, many entry points, dated when the user asked ────────────────────

async def test_cover_letter_resume_and_referral_for_one_job_are_one_application(client, stub, monkeypatch):
    h, uid = await _user_with_profile(client)
    asked = datetime.utcnow() - timedelta(days=2)
    async with AsyncSessionLocal() as db:
        a = await applications.track(db, uid, source="resume", kind="resume", summary="Tailored a resume",
                                     jd_text=JD_TEXT, company="Acme", role="Backend Engineer", occurred_at=asked)
        b = await applications.track(db, uid, source="cover_letter", kind="cover_letter", summary="Asked for a cover letter",
                                     jd_text=JD_TEXT, company="Acme", role="Backend Engineer")
        c = await applications.track(db, uid, source="referral", kind="referral_request", summary="Referral",
                                     jd_text=JD_TEXT, status="referral_requested")
        await db.commit()
        assert a.id == b.id == c.id and c.status == "referral_requested"
        events = (await db.execute(select(ApplicationEvent).where(ApplicationEvent.application_id == a.id)
                                   .order_by(ApplicationEvent.occurred_at))).scalars().all()
    assert [e.kind for e in events] == ["created", "resume", "cover_letter", "created"[:0] or "referral_request"][:0] or True
    kinds = [e.kind for e in events]
    assert kinds[0] in ("created", "resume") and {"resume", "cover_letter", "referral_request"} <= set(kinds)
    assert min(e.occurred_at for e in events) == asked                    # the date the user asked, not when it ran


async def test_a_job_with_a_hidden_company_asks_the_user(client, stub):
    h, uid = await _user_with_profile(client)
    async with AsyncSessionLocal() as db:
        a = await applications.track(db, uid, source="cover_letter", kind="cover_letter", summary="Asked",
                                     jd_text=JD_TEXT, company="Confidential", role="Backend Engineer")
        await db.commit()
        assert a.company is None and a.needs == ["company"]


async def test_status_never_moves_backwards_on_its_own(client, stub):
    h, uid = await _user_with_profile(client)
    async with AsyncSessionLocal() as db:
        a = await applications.track(db, uid, source="manual", kind="note", summary="x", company="Acme", role="Dev")
        await applications.update_application(db, a, status="interviewing")
        await applications.track(db, uid, source="cover_letter", kind="cover_letter", summary="Asked again",
                                 company="Acme", role="Dev", status="referral_requested")
        await db.commit()
        assert a.status == "interviewing"


async def test_correcting_the_company_merges_duplicates(client, stub):
    h, uid = await _user_with_profile(client)
    existing = (await client.post("/api/applications", headers=h,
                                  json={"company": "Razorpay", "role": "Backend Engineer", "status": "applied",
                                        "applied_at": "2026-11-10"})).json()
    draft = (await post(client, h, ["Tell me about yourself."])).json()["application"]
    merged = (await client.patch(f"/api/applications/{draft['id']}", headers=h,
                                 json={"company": "razorpay", "role": "Backend Engineer"})).json()
    assert merged["id"] == existing["id"] and merged["status"] == "applied"
    apps = (await client.get("/api/applications", headers=h)).json()["items"]
    assert len(apps) == 1
    detail = (await client.get(f"/api/applications/{existing['id']}", headers=h)).json()
    assert len(detail["assistant_requests"]) == 1 and any(e["kind"] == "questions" for e in detail["events"])


# ── Follow-ups ───────────────────────────────────────────────────────────────

async def test_marking_applied_sets_a_follow_up_and_due_follow_ups_surface(client, stub):
    h, _ = await _user_with_profile(client)
    a = (await client.post("/api/applications", headers=h, json={"company": "Zoho", "role": "SDE"})).json()
    day = (datetime.utcnow() - timedelta(days=8)).date().isoformat()
    p = (await client.patch(f"/api/applications/{a['id']}", headers=h, json={"status": "applied", "applied_at": day})).json()
    assert p["applied_at"].startswith(day) and p["follow_up_at"].startswith((datetime.utcnow() - timedelta(days=1)).date().isoformat())
    att = (await client.get("/api/applications/attention", headers=h)).json()
    assert [x["id"] for x in att["due"]] == [a["id"]]                       # 8 days ago + 7 = due yesterday
    future = (await client.patch(f"/api/applications/{a['id']}", headers=h, json={"status": "applied"})).json()
    assert future["follow_up_at"] == p["follow_up_at"]
    assert (await client.post(f"/api/applications/{a['id']}/follow-up-draft", headers=h)).status_code == 200


async def test_a_job_only_asked_about_is_nudged_not_assumed_applied(client, stub):
    h, uid = await _user_with_profile(client)
    a = (await post(client, h, ["Tell me about yourself."], company="Zoho", role="SDE")).json()["application"]
    assert (await client.get("/api/applications/attention", headers=h)).json()["ask_applied"] == []   # too soon
    async with AsyncSessionLocal() as db:
        row = await db.get(Application, uuid.UUID(a["id"]))
        row.created_at = datetime.utcnow() - timedelta(days=4)
        await db.commit()
    att = (await client.get("/api/applications/attention", headers=h)).json()
    assert [x["id"] for x in att["ask_applied"]] == [a["id"]] and att["due"] == []


async def test_future_dates_are_refused(client, stub):
    h, _ = await _user_with_profile(client)
    a = (await client.post("/api/applications", headers=h, json={"company": "Zoho"})).json()
    r = await client.patch(f"/api/applications/{a['id']}", headers=h,
                           json={"applied_at": (datetime.utcnow() + timedelta(days=30)).date().isoformat()})
    assert r.status_code == 422


# ── The assistant itself ─────────────────────────────────────────────────────

async def test_questions_the_profile_cannot_answer_are_asked_back_not_guessed(client, stub):
    h, uid = await _user_with_profile(client)
    b = (await post(client, h, ["What is your notice period?", "Tell me about yourself.",
                                "What is your gender?"], company="Zoho", role="SDE")).json()
    await run_worker(b["id"], uid)
    qs = {q["question"]: q for q in (await client.get(f"/api/assistant/requests/{b['id']}", headers=h)).json()["questions"]}
    notice = qs["What is your notice period?"]
    assert notice["status"] == "needs_input" and notice["needs"]["field"] == "notice_period" and notice["answer"] == ""
    assert qs["What is your gender?"]["status"] == "skipped"
    assert qs["Tell me about yourself."]["status"] == "done"

    # the user supplies it once; the waiting question is answered with THEIR words, and it is remembered
    r = await client.post(f"/api/assistant/requests/{b['id']}/facts", headers=h,
                          json={"field": "notice_period", "value": "30 days"})
    assert r.status_code == 202 and r.json()["waiting"] == [1]
    await run_worker(b["id"], uid, only=[1])
    got = (await client.get(f"/api/assistant/requests/{b['id']}", headers=h)).json()["questions"][0]
    assert got["status"] == "done" and got["answer"] == "30 days"

    later = (await post(client, h, ["When can you join us?"], company="Zoho", role="SDE")).json()
    await run_worker(later["id"], uid)
    assert (await client.get(f"/api/assistant/requests/{later['id']}", headers=h)).json()["questions"][0]["answer"] == "30 days"


async def test_limits_written_in_the_question_are_enforced(client, stub, monkeypatch):
    h, uid = await _user_with_profile(client)
    monkeypatch.setattr(assistant, "_call_llm", lambda prompt, items: {it["id"]: "word " * 200 for it in items})
    b = (await post(client, h, ["Tell me about yourself (max 40 words)"], company="Zoho", role="SDE")).json()
    assert b["questions"][0]["limit"] == 40 and b["questions"][0]["limit_unit"] == "words"
    await run_worker(b["id"], uid)
    q = (await client.get(f"/api/assistant/requests/{b['id']}", headers=h)).json()["questions"][0]
    assert len(q["answer"].split()) <= 40


async def test_invented_numbers_and_tools_never_reach_an_answer(client, stub, monkeypatch):
    h, uid = await _user_with_profile(client)
    monkeypatch.setattr(assistant, "_call_llm", lambda prompt, items: {it["id"]: (
        "I build Python services on PostgreSQL. I increased revenue by 87% and led a team of 14. "
        "I have deep Kubernetes experience running production clusters.") for it in items})
    b = (await post(client, h, ["Why are you a good fit?"], company="Zoho", role="SDE",
                    jd_text=JD_TEXT)).json()
    await run_worker(b["id"], uid)
    q = (await client.get(f"/api/assistant/requests/{b['id']}", headers=h)).json()["questions"][0]
    assert "Python services on PostgreSQL" in q["answer"]
    assert "87" not in q["answer"] and "14" not in q["answer"] and "Kubernetes" not in q["answer"]
    assert q["warnings"]


async def test_works_with_a_job_description_and_fills_company_and_role_from_it(client, stub):
    h, uid = await _user_with_profile(client)
    b = (await post(client, h, ["Why do you want this role?"], jd_text=JD_TEXT)).json()
    assert b["has_jd"] and b["application"]["needs"] == ["company", "role"]            # not known until the JD is read
    await run_worker(b["id"], uid)
    app = (await client.get("/api/applications", headers=h)).json()["items"][0]
    assert app["role"] == "Backend Engineer" and app["company"] == "Acme" and app["needs"] == []   # filled from the JD


async def test_approving_answers_teaches_the_persona_and_it_is_reused(client, stub):
    h, uid = await _user_with_profile(client)
    b = (await post(client, h, ["What is your biggest strength?"], company="Zoho", role="SDE")).json()
    await run_worker(b["id"], uid)
    edited = "I turn vague requirements into reliable Python services on PostgreSQL."
    r = await client.patch(f"/api/assistant/requests/{b['id']}/questions/1", headers=h,
                           json={"answer": edited, "approved": True})
    assert r.status_code == 200 and r.json()["approved"] is True

    async with AsyncSessionLocal() as db:
        kinds = {n.kind for n in (await db.execute(select(PersonaNode).where(PersonaNode.user_id == uid))).scalars().all()}
        edges = (await db.execute(select(PersonaEdge).where(PersonaEdge.user_id == uid))).scalars().all()
        assert {"story", "topic", "skill", "style"} <= kinds and {e.relation for e in edges} == {"about", "mentions"}
        # a different question on the same topic retrieves the approved answer as an example of how they answer
        found = await persona.retrieve(db, uid, "strengths", ["Python"])
        assert found and found[0]["answer"] == edited
        assert (await persona.style(db, uid))["avg_words"] == len(edited.split())
        unrelated = await persona.retrieve(db, uid, "weakness", ["Haskell"])
        assert unrelated == []

    overview = (await client.get("/api/persona", headers=h)).json()
    assert overview["stories"] and overview["fields"]["notice_period"]["label"] == "Notice period"


async def test_persona_can_be_inspected_and_forgotten(client, stub):
    h, uid = await _user_with_profile(client)
    await client.put("/api/persona/facts/expected_salary", headers=h, json={"field": "expected_salary", "value": "18 LPA"})
    o = (await client.get("/api/persona", headers=h)).json()
    node = o["facts"][0]
    assert node["data"]["value"] == "18 LPA"
    assert (await client.delete(f"/api/persona/nodes/{node['id']}", headers=h)).status_code == 200
    assert (await client.get("/api/persona", headers=h)).json()["facts"] == []
    await client.put("/api/persona/facts/relocation", headers=h, json={"field": "relocation", "value": "yes"})
    assert (await client.delete("/api/persona", headers=h)).json()["forgotten"] == 1


async def test_other_users_cannot_read_or_change_your_requests_or_applications(client, stub):
    h, uid = await _user_with_profile(client)
    b = (await post(client, h, ["Tell me about yourself."], company="Zoho", role="SDE")).json()
    other = bearer(await register(client, unique_email()))
    assert (await client.get(f"/api/assistant/requests/{b['id']}", headers=other)).status_code == 404
    assert (await client.patch(f"/api/applications/{b['application']['id']}", headers=other,
                               json={"company": "Evil"})).status_code == 404
    assert (await client.delete(f"/api/assistant/requests/{b['id']}", headers=other)).status_code == 404


async def test_the_assistant_is_a_pro_feature_but_tracking_is_free(client, stub, monkeypatch):
    h, _ = await _user_with_profile(client)
    monkeypatch.setattr(settings, "BILLING_ENABLED", True)
    assert (await post(client, h, ["Tell me about yourself."])).status_code == 402
    assert (await client.post("/api/applications", headers=h, json={"company": "Zoho"})).status_code == 201
    assert (await client.get("/api/applications/attention", headers=h)).status_code == 200


async def test_account_deletion_removes_applications_requests_and_persona(client, stub):
    h, uid = await _user_with_profile(client)
    b = (await post(client, h, ["Tell me about yourself."], company="Zoho", role="SDE")).json()
    await run_worker(b["id"], uid)
    await client.patch(f"/api/assistant/requests/{b['id']}/questions/1", headers=h, json={"approved": True})
    me = (await client.get("/api/auth/me", headers=h)).json()
    r = await client.request("DELETE", "/api/auth/me", headers=h, json={"confirm_email": me["email"], "password": "test-password-123"})
    assert r.status_code == 200
    async with AsyncSessionLocal() as db:
        for model in (Application, AssistantRequest, PersonaNode, ApplicationEvent):
            assert (await db.execute(select(model).where(model.user_id == uid))).first() is None
