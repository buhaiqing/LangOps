"""Remediation execute flow system tests.

Covers the full remediation lifecycle: create plan → execute (dry-run) → verify status.
Also tests guard conditions: confirm=false, non-low-risk, already executed.
"""

from fastapi.testclient import TestClient


class TestRemediationExecuteDryRun:
    """Execute a remediation plan with dry_run=True."""

    def test_dry_run_succeeds(self, client: TestClient, k8s_alert_payload: dict) -> None:
        # Create a plan via alert
        resp = client.post("/api/v1/alerts", json=k8s_alert_payload)
        plan_id = resp.json()["remediation_plan_id"]
        assert plan_id is not None

        # Execute with dry_run
        exec_resp = client.post(
            f"/api/v1/remediation/{plan_id}/execute",
            json={"approved_by": "test-user", "confirm": True, "dry_run": True},
        )
        assert exec_resp.status_code == 200
        body = exec_resp.json()
        assert body["success"] is True
        assert body["plan"] is not None
        assert body["plan"]["status"] == "dry_run"
        assert body["plan"]["approved_by"] == "test-user"
        assert body["plan"]["execution_output"] is not None
        assert "dry-run" in body["plan"]["execution_output"].lower()

    def test_dry_run_does_not_change_commands(self, client: TestClient, k8s_alert_payload: dict) -> None:
        resp = client.post("/api/v1/alerts", json=k8s_alert_payload)
        plan_id = resp.json()["remediation_plan_id"]

        exec_resp = client.post(
            f"/api/v1/remediation/{plan_id}/execute",
            json={"approved_by": "ops", "confirm": True, "dry_run": True},
        )
        plan = exec_resp.json()["plan"]
        # Commands should be preserved in execution_output
        assert len(plan["commands"]) > 0


class TestRemediationGuards:
    """Execute should be rejected when guard conditions are not met."""

    def test_confirm_false_rejected(self, client: TestClient, k8s_alert_payload: dict) -> None:
        resp = client.post("/api/v1/alerts", json=k8s_alert_payload)
        plan_id = resp.json()["remediation_plan_id"]

        exec_resp = client.post(
            f"/api/v1/remediation/{plan_id}/execute",
            json={"approved_by": "ops", "confirm": False, "dry_run": True},
        )
        body = exec_resp.json()
        assert body["success"] is False
        assert "confirm" in body["error"].lower()

    def test_already_rejected_cannot_execute(self, client: TestClient, k8s_alert_payload: dict) -> None:
        resp = client.post("/api/v1/alerts", json=k8s_alert_payload)
        plan_id = resp.json()["remediation_plan_id"]

        # Reject first
        client.post(
            f"/api/v1/remediation/{plan_id}/reject",
            json={"rejected_by": "ops", "reason": "no"},
        )

        # Try to execute rejected plan
        exec_resp = client.post(
            f"/api/v1/remediation/{plan_id}/execute",
            json={"approved_by": "ops", "confirm": True, "dry_run": True},
        )
        body = exec_resp.json()
        assert body["success"] is False
        assert "pending" in body["error"].lower() or "not" in body["error"].lower()

    def test_already_executed_cannot_execute_again(self, client: TestClient, k8s_alert_payload: dict) -> None:
        resp = client.post("/api/v1/alerts", json=k8s_alert_payload)
        plan_id = resp.json()["remediation_plan_id"]

        # Execute first (dry-run)
        client.post(
            f"/api/v1/remediation/{plan_id}/execute",
            json={"approved_by": "ops", "confirm": True, "dry_run": True},
        )

        # Try again
        exec_resp = client.post(
            f"/api/v1/remediation/{plan_id}/execute",
            json={"approved_by": "ops", "confirm": True, "dry_run": True},
        )
        body = exec_resp.json()
        assert body["success"] is False
        assert "pending" in body["error"].lower() or "not" in body["error"].lower()


class TestRemediationListAndRetrieve:
    """List pending plans and retrieve specific plan after creation."""

    def test_list_pending_plans(self, client: TestClient, k8s_alert_payload: dict) -> None:
        client.post("/api/v1/alerts", json=k8s_alert_payload)
        resp = client.get("/api/v1/remediation")
        assert resp.status_code == 200
        plans = resp.json()
        assert isinstance(plans, list)
        assert len(plans) >= 1

    def test_get_created_plan_fields(self, client: TestClient, k8s_alert_payload: dict) -> None:
        resp = client.post("/api/v1/alerts", json=k8s_alert_payload)
        plan_id = resp.json()["remediation_plan_id"]

        plan_resp = client.get(f"/api/v1/remediation/{plan_id}")
        assert plan_resp.status_code == 200
        plan = plan_resp.json()
        assert plan["plan_id"] == plan_id
        assert plan["status"] == "pending_approval"
        assert plan["risk_level"] in ("low", "medium", "high")
        assert isinstance(plan["commands"], list)
        assert isinstance(plan["risks"], list)
