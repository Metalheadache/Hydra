"""
Tests for Brain — task decomposition with mocked LLM.
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from hydra.brain import Brain, _extract_json
from hydra.config import HydraConfig
from hydra.models import TaskPlan
from hydra.tool_registry import ToolRegistry


def make_config() -> HydraConfig:
    return HydraConfig(api_key="test-key", brain_model="anthropic/claude-sonnet-4-6")


def make_valid_plan_dict() -> dict:
    """Return a minimal valid TaskPlan dict."""
    return {
        "task_id": "task_abc123",
        "original_task": "Do research",
        "sub_tasks": [
            {
                "id": "st_aaa",
                "description": "Research topic A",
                "expected_output": "A summary of topic A",
                "dependencies": [],
                "priority": "normal",
            },
            {
                "id": "st_bbb",
                "description": "Synthesize findings",
                "expected_output": "A report",
                "dependencies": ["st_aaa"],
                "priority": "normal",
            },
        ],
        "agent_specs": [
            {
                "agent_id": "agent_001",
                "sub_task_id": "st_aaa",
                "role": "Research Analyst",
                "goal": "Research topic A thoroughly",
                "backstory": "Expert researcher",
                "tools_needed": [],
                "constraints": [],
                "temperature": 0.4,
            },
            {
                "agent_id": "agent_002",
                "sub_task_id": "st_bbb",
                "role": "Report Writer",
                "goal": "Write report",
                "backstory": "Expert writer",
                "tools_needed": [],
                "constraints": [],
                "temperature": 0.4,
            },
        ],
        "execution_groups": [["st_aaa"], ["st_bbb"]],
    }


def make_mock_response(content: str):
    """Create a mock litellm response object."""
    msg = MagicMock()
    msg.content = content
    choice = MagicMock()
    choice.message = msg
    resp = MagicMock()
    resp.choices = [choice]
    resp.usage = None
    return resp


@pytest.fixture
def registry() -> ToolRegistry:
    return ToolRegistry()  # Empty registry for tests


@pytest.mark.asyncio
async def test_brain_produces_valid_plan(registry):
    config = make_config()
    brain = Brain(config, registry)

    plan_dict = make_valid_plan_dict()
    mock_resp = make_mock_response(json.dumps(plan_dict))

    with patch("litellm.acompletion", new_callable=AsyncMock, return_value=mock_resp):
        plan = await brain.plan("Do research on topic A")

    assert isinstance(plan, TaskPlan)
    assert len(plan.sub_tasks) == 2
    assert len(plan.agent_specs) == 2
    assert plan.execution_groups == [["st_aaa"], ["st_bbb"]]


@pytest.mark.asyncio
async def test_brain_retries_on_invalid_json(registry):
    config = make_config()
    brain = Brain(config, registry)

    plan_dict = make_valid_plan_dict()
    invalid_response = make_mock_response("This is not JSON at all, sorry!")
    valid_response = make_mock_response(json.dumps(plan_dict))

    with patch(
        "litellm.acompletion",
        new_callable=AsyncMock,
        side_effect=[invalid_response, valid_response],
    ):
        plan = await brain.plan("Do research")

    assert isinstance(plan, TaskPlan)


@pytest.mark.asyncio
async def test_brain_fails_after_max_retries(registry):
    config = make_config()
    brain = Brain(config, registry)

    bad_response = make_mock_response("definitely not json")

    with patch(
        "litellm.acompletion",
        new_callable=AsyncMock,
        return_value=bad_response,
    ):
        with pytest.raises(ValueError, match="failed to produce"):
            await brain.plan("Some task")


@pytest.mark.asyncio
async def test_brain_rejects_inconsistent_plan(registry):
    """Plan where execution_groups reference unknown sub_task_ids should fail."""
    config = make_config()
    brain = Brain(config, registry)

    bad_plan = make_valid_plan_dict()
    bad_plan["execution_groups"] = [["st_nonexistent"]]
    response = make_mock_response(json.dumps(bad_plan))

    with patch("litellm.acompletion", new_callable=AsyncMock, side_effect=[response, response, response]):
        with pytest.raises(ValueError):
            await brain.plan("Task")


def test_extract_json_from_fence():
    text = '```json\n{"key": "value"}\n```'
    extracted = _extract_json(text)
    assert json.loads(extracted) == {"key": "value"}


def test_extract_json_bare():
    text = 'Here is the result:\n{"key": 42}\nDone.'
    extracted = _extract_json(text)
    assert json.loads(extracted) == {"key": 42}


def test_extract_json_plain():
    text = '{"key": true}'
    extracted = _extract_json(text)
    assert json.loads(extracted) == {"key": True}
