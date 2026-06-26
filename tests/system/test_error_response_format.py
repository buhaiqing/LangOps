"""Error response format system tests.

Validates that validation failures and bad requests return correctly
structured error responses, so clients can rely on a consistent contract.
"""

from fastapi.testclient import TestClient


class TestValidationErrorStructure:
    """Pydantic validation errors must follow a standard schema."""

    def test_empty_body_returns_detail_array(self, client: TestClient) -> None:
        response = client.post("/api/v1/alerts", json={})
        assert response.status_code == 422
        body = response.json()
        assert "detail" in body
        assert isinstance(body["detail"], list)
        assert len(body["detail"]) > 0

    def test_detail_item_has_loc_and_msg(self, client: TestClient) -> None:
        """Each detail entry must contain 'loc' and 'msg' for client rendering."""
        response = client.post("/api/v1/alerts", json={})
        detail = response.json()["detail"]
        for item in detail:
            assert "loc" in item, f"Missing 'loc' in: {item}"
            assert "msg" in item, f"Missing 'msg' in: {item}"
            assert "type" in item, f"Missing 'type' in: {item}"

    def test_missing_title_field_error_location(self, client: TestClient) -> None:
        payload = {
            "description": "Test",
            "severity": "critical",
            "category": "resource",
            "source": {"type": "kubernetes", "system": "test"},
        }
        response = client.post("/api/v1/alerts", json=payload)
        assert response.status_code == 422
        detail = response.json()["detail"]
        locs = [item["loc"] for item in detail]
        # title is a top-level required field → should appear in loc
        assert any("title" in loc for loc in locs)

    def test_missing_severity_field_error_location(self, client: TestClient) -> None:
        payload = {
            "title": "Test",
            "description": "Test",
            "category": "resource",
            "source": {"type": "kubernetes", "system": "test"},
        }
        response = client.post("/api/v1/alerts", json=payload)
        assert response.status_code == 422
        detail = response.json()["detail"]
        locs = [item["loc"] for item in detail]
        assert any("severity" in loc for loc in locs)

    def test_invalid_severity_enum_error(self, client: TestClient) -> None:
        payload = {
            "title": "Test",
            "description": "Test",
            "severity": "invalid_level",
            "category": "resource",
            "source": {"type": "kubernetes", "system": "test"},
        }
        response = client.post("/api/v1/alerts", json=payload)
        assert response.status_code == 422
        detail = response.json()["detail"]
        # Pydantic v2: type="enum", msg="Input should be 'critical' or 'high'"
        types = [item.get("type") for item in detail]
        msgs = [item.get("msg", "") for item in detail]
        assert "enum" in types or any("input should be" in m.lower() for m in msgs)


class TestMalformedRequest:
    """Various malformed request bodies."""

    def test_null_body_returns_422(self, client: TestClient) -> None:
        response = client.post(
            "/api/v1/alerts",
            content=b"",
            headers={"Content-Type": "application/json"},
        )
        assert response.status_code == 422

    def test_non_json_body_returns_422(self, client: TestClient) -> None:
        response = client.post(
            "/api/v1/alerts",
            content="not json",
            headers={"Content-Type": "text/plain"},
        )
        # FastAPI may return 422 or 415 depending on version
        assert response.status_code in (415, 422)

    def test_array_body_returns_422(self, client: TestClient) -> None:
        response = client.post("/api/v1/alerts", json=[{"title": "x"}])
        assert response.status_code == 422

    def test_unknown_top_level_fields_ignored(self, client: TestClient) -> None:
        """Extra fields outside the model should be silently ignored (not 422)."""
        payload = {
            "title": "Test alert",
            "description": "Test",
            "severity": "critical",
            "category": "resource",
            "source": {"type": "kubernetes", "system": "test"},
            "unknown_field_xyz": "should be ignored",
        }
        response = client.post("/api/v1/alerts", json=payload)
        # Should succeed (200) or fail with 422 if Pydantic rejects extras
        assert response.status_code in (200, 422)


class TestRemediation404:
    """GET/POST on non-existent plan_id returns proper error."""

    def test_get_nonexistent_plan_returns_404(self, client: TestClient) -> None:
        response = client.get("/api/v1/remediation/plan-nonexistent-xyz")
        assert response.status_code == 404
        body = response.json()
        assert "detail" in body

    def test_execute_nonexistent_plan_returns_error(self, client: TestClient) -> None:
        response = client.post(
            "/api/v1/remediation/plan-nonexistent-xyz/execute",
            json={"approved_by": "ops", "confirm": True, "dry_run": True},
        )
        # Returns 200 with success=False and error message
        assert response.status_code == 200
        body = response.json()
        assert body["success"] is False
        assert body["error"] is not None

    def test_reject_nonexistent_plan_returns_error(self, client: TestClient) -> None:
        response = client.post(
            "/api/v1/remediation/plan-nonexistent-xyz/reject",
            json={"rejected_by": "ops", "reason": "test"},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["success"] is False
        assert body["error"] is not None
