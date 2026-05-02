"""Integration smoke test: full API CRUD flow."""
import json


async def test_health(client):
    r = await client.get("/api/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok", "version": "0.1.0"}


async def test_company_styles_list_empty(client):
    r = await client.get("/api/company-styles")
    assert r.status_code == 200
    assert r.json() == []


async def test_company_styles_upload_and_list(client):
    payload = {
        "name": "ACME",
        "interviewer_style_tags": ["friendly"],
        "preferred_question_types": ["tech"],
        "sample_questions": [],
    }
    r = await client.post(
        "/api/company-styles",
        files={"file": ("style.json", json.dumps(payload).encode(), "application/json")},
    )
    assert r.status_code == 201, r.text
    cs = r.json()
    assert cs["name"] == "ACME"

    r = await client.get("/api/company-styles")
    assert len(r.json()) == 1


async def test_company_styles_upload_bad_json(client):
    r = await client.post(
        "/api/company-styles",
        files={"file": ("bad.json", b"{not json", "application/json")},
    )
    assert r.status_code == 400
    assert r.json()["detail"]["error"] == "bad_request"


async def test_interview_crud_flow(client):
    # create
    r = await client.post(
        "/api/interviews",
        json={"company_name": "某公司", "role_title": "RF Intern", "language": "zh"},
    )
    assert r.status_code == 201, r.text
    iv = r.json()
    iid = iv["id"]
    assert iv["company_name"] == "某公司"
    assert iv["status"] == "in_progress"

    # list
    r = await client.get("/api/interviews")
    assert r.status_code == 200
    assert any(i["id"] == iid for i in r.json())

    # detail
    r = await client.get(f"/api/interviews/{iid}")
    assert r.status_code == 200
    assert r.json()["id"] == iid

    # delete
    r = await client.delete(f"/api/interviews/{iid}")
    assert r.status_code == 204

    # not found after delete
    r = await client.get(f"/api/interviews/{iid}")
    assert r.status_code == 404


async def test_interview_not_found(client):
    r = await client.get("/api/interviews/nonexistent")
    assert r.status_code == 404


async def test_interview_create_validation_error(client):
    r = await client.post("/api/interviews", json={"company_name": ""})
    assert r.status_code == 422


async def test_audio_url_not_found(client):
    # create an interview with no questions → segment 0 out of range
    r = await client.post(
        "/api/interviews", json={"company_name": "X", "role_title": "Y"}
    )
    iid = r.json()["id"]
    r = await client.get(f"/api/interviews/{iid}/audio/0")
    assert r.status_code == 404
