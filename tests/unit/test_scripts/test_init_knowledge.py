"""Init knowledge script tests."""

import importlib.util
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from langops.models import AlertCreate

ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "scripts" / "init_knowledge.py"
SAMPLE_ALERT = ROOT / "docs" / "examples" / "sample-alert.json"


def _load_init_module():
    spec = importlib.util.spec_from_file_location("init_knowledge", SCRIPT)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_sample_alert_json_matches_alert_create() -> None:
    data = json.loads(SAMPLE_ALERT.read_text(encoding="utf-8"))
    alert = AlertCreate.model_validate(data)
    assert alert.title == "CPU使用率过高"
    assert alert.severity.value == "critical"


@pytest.mark.asyncio
async def test_init_knowledge_base_adds_all_sample_cases() -> None:
    mod = _load_init_module()
    mock_store = MagicMock()
    mock_store.add_case = AsyncMock(return_value="a" * 32)
    mock_store.count = AsyncMock(return_value=len(mod.SAMPLE_CASES))

    with patch.object(mod, "VectorStore", return_value=mock_store):
        await mod.init_knowledge_base()

    assert mock_store.add_case.await_count == len(mod.SAMPLE_CASES)
    mock_store.count.assert_awaited_once()
