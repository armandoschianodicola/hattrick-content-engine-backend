from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

from hattrick_backend.domain.enums import Platform, PublicationStatus
from hattrick_backend.infrastructure.publishing.base import PublishResult


async def draft(client, platforms=None):
    response = await client.post(
        "/api/v1/generations",
        json={"topic_id": "weather", "target_platforms": platforms or ["telegram"]},
    )
    assert response.status_code == 201, response.text
    return response.json()


async def approve(client, post):
    url = f"/api/v1/posts/{post['id']}"
    for action in ("submit-review", "approve"):
        response = await client.post(
            f"{url}/{action}", json={"expected_revision": post["revision"]}
        )
        assert response.status_code == 200, response.text


async def test_complete_workflow(client):
    assert (await client.get("/health")).status_code == 200
    assert (await client.get("/api/v1/topics")).json()["total"] == 5
    assert len((await client.get("/api/v1/topics/weather/context")).json()["items"]) == 2
    post = await draft(client)
    url = f"/api/v1/posts/{post['id']}"
    assert (await client.get(url)).json()["state"] == "DRAFT"
    post["content"]["title"] = "Edited weather research checklist"
    response = await client.patch(url, json={"expected_revision": 1, "content": post["content"]})
    assert response.status_code == 200, response.text
    post = response.json()
    assert post["revision"] == 2
    await approve(client, post)
    asset = await client.post(f"{url}/render", json={})
    assert asset.status_code == 201, asset.text
    download = await client.get(asset.json()["download_url"])
    assert download.content.startswith(b"\x89PNG")
    assert (await client.get(f"{url}/assets")).json()["total"] == 1
    payload = {"platforms": ["telegram"], "idempotency_key": "workflow-001"}
    first = await client.post(f"{url}/publish", json=payload)
    assert first.status_code == 200, first.text
    assert first.json()["items"][0]["status"] == "SUCCEEDED"
    assert (await client.get(url)).json()["state"] == "PUBLISHED"
    again = await client.post(f"{url}/publish", json=payload)
    assert again.json() == first.json()
    payload["idempotency_key"] = "workflow-002"
    assert (await client.post(f"{url}/publish", json=payload)).json() == first.json()
    assert (await client.get(f"{url}/publications")).json()["total"] == 1
    assert (await client.get(f"{url}/revisions")).json()["total"] == 2
    assert (await client.get(f"{url}/history")).json()["total"] == 3
    assert (await client.get("/api/v1/posts?state=PUBLISHED&limit=1")).json()["total"] == 1


async def test_auth_and_validation(client):
    missing = await client.get("/api/v1/unknown-endpoint")
    assert missing.status_code == 404 and "error" in missing.json()
    for path in ("/api/v1/topics", "/api/v1/posts"):
        assert (await client.get(path, headers={"X-API-Key": "bad"})).status_code == 401
    assert (await client.get("/api/v1/posts/not-a-uuid")).status_code == 422
    assert (await client.get("/api/v1/posts?limit=1000")).status_code == 422
    response = await client.post(
        "/api/v1/generations",
        json={"topic_id": "weather", "target_platforms": ["telegram", "telegram"]},
    )
    assert response.status_code == 422 and "error" in response.json()
    assert (await client.get("/api/v1/topics/missing")).status_code == 404
    assert (
        await client.post("/api/v1/generations", json={"topic_id": "tactics"})
    ).status_code == 422


async def test_review_reject_reopen_conflicts(client):
    post = await draft(client)
    url = f"/api/v1/posts/{post['id']}"
    action = {"expected_revision": 1}
    assert (await client.post(f"{url}/approve", json=action)).status_code == 409
    assert (
        await client.post(
            f"{url}/publish", json={"platforms": ["telegram"], "idempotency_key": "blocked-001"}
        )
    ).status_code == 409
    assert (await client.post(f"{url}/submit-review", json=action)).status_code == 200
    assert (await client.post(f"{url}/reject", json=action)).json()["state"] == "REJECTED"
    assert (await client.post(f"{url}/reopen", json=action)).json()["state"] == "DRAFT"
    assert (
        await client.patch(url, json={"expected_revision": 9, "content": post["content"]})
    ).status_code == 409
    await approve(client, post)
    assert (
        await client.patch(url, json={"expected_revision": 1, "content": post["content"]})
    ).status_code == 409
    assert (
        await client.post(f"{url}/approve", json=action, headers={"X-API-Key": "bad"})
    ).status_code == 401
    assert (
        await client.post(
            f"{url}/publish",
            json={"platforms": ["telegram"], "idempotency_key": "blocked-002"},
            headers={"X-API-Key": "bad"},
        )
    ).status_code == 401


async def test_platform_failure_is_independent_and_retry_safe(client, app):
    post = await draft(client, ["telegram", "instagram"])
    await approve(client, post)
    url = f"/api/v1/posts/{post['id']}"
    response = await client.post(
        f"{url}/publish",
        json={"platforms": ["telegram", "instagram"], "idempotency_key": "multi-001"},
    )
    assert response.status_code == 200, response.text
    assert [i["status"] for i in response.json()["items"]] == ["SUCCEEDED", "FAILED"]
    assert (await client.get(url)).json()["state"] == "APPROVED"
    assert (await client.get(f"{url}/publications")).json()["total"] == 2
    await client.post(
        f"{url}/publish", json={"platforms": ["instagram"], "idempotency_key": "multi-001"}
    )
    assert (await client.get(f"{url}/publications")).json()["total"] == 2
    await client.post(
        f"{url}/publish", json={"platforms": ["instagram"], "idempotency_key": "multi-002"}
    )
    assert (await client.get(f"{url}/publications")).json()["total"] == 3


async def test_unknown_outcome_blocks_new_attempt(client, app):
    publisher = AsyncMock()
    publisher.publish.return_value = PublishResult(
        Platform.TELEGRAM, PublicationStatus.UNKNOWN, error_code="outcome_unknown"
    )
    app.state.publishers[Platform.TELEGRAM] = publisher
    post = await draft(client)
    await approve(client, post)
    url = f"/api/v1/posts/{post['id']}/publish"
    first = {"platforms": ["telegram"], "idempotency_key": "unknown-001"}
    assert (await client.post(url, json=first)).json()["items"][0]["status"] == "UNKNOWN"
    assert (await client.post(url, json=first)).status_code == 200
    first["idempotency_key"] = "unknown-002"
    assert (await client.post(url, json=first)).status_code == 409
    assert publisher.publish.await_count == 1


async def test_schedule_and_due_guard(client):
    post = await draft(client)
    await approve(client, post)
    url = f"/api/v1/posts/{post['id']}"
    response = await client.post(
        f"{url}/schedule",
        json={
            "expected_revision": 1,
            "scheduled_at": (datetime.now(UTC) + timedelta(days=1)).isoformat(),
        },
    )
    assert response.status_code == 200, response.text
    response = await client.post(
        f"{url}/publish", json={"platforms": ["telegram"], "idempotency_key": "not-due-001"}
    )
    assert response.status_code == 409 and response.json()["error"]["code"] == "not_due"


async def test_unexpected_error_never_exposes_credentials(client, app, caplog):
    app.state.ai = AsyncMock()
    app.state.ai.generate.side_effect = RuntimeError("database-password-and-bot-token")
    response = await client.post("/api/v1/generations", json={"topic_id": "weather"})
    assert response.status_code == 500
    assert response.json()["error"]["code"] == "internal_error"
    assert "database-password-and-bot-token" not in response.text + caplog.text
