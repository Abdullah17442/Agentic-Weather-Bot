import asyncio
from pathlib import Path

from google.adk.cli.utils.agent_loader import AgentLoader

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def load_root_agent():
    """Load the agent exactly the way `adk run` / `adk web` discover it."""
    return AgentLoader(str(PROJECT_ROOT)).load_agent("weather_agent")


def test_adk_loads_root_agent_using_gemini_3_6_flash():
    agent = load_root_agent()

    assert agent.model == "gemini-3.6-flash"


def test_gemini_is_offered_get_weather_tool_taking_a_city():
    agent = load_root_agent()

    tools = asyncio.run(agent.canonical_tools())
    # _get_declaration() is ADK's method that builds the schema Gemini receives.
    declarations = {tool.name: tool._get_declaration() for tool in tools}

    assert "get_weather" in declarations
    schema = declarations["get_weather"].parameters_json_schema
    assert schema["properties"]["city"]["type"] == "string"
    assert schema["required"] == ["city"]


def test_agent_has_only_the_get_weather_tool():
    """Least privilege: a hijacked prompt can only ever trigger a read-only weather lookup."""
    agent = load_root_agent()

    tools = asyncio.run(agent.canonical_tools())

    assert [tool.name for tool in tools] == ["get_weather"]
