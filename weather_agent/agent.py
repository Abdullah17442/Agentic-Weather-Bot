"""The ADK agent definition. `adk run` / `adk web` discover `root_agent` here."""

from google.adk.agents import Agent

from .weather import get_weather

root_agent = Agent(
    name="weather_agent",
    model="gemini-3.5-flash",
    description="Answers questions about the current weather in a city.",
    instruction=(
        "You are a friendly weather assistant.\n"
        "When the user asks about the weather, identify the city they mention and "
        "call the `get_weather` tool with that city name.\n"
        "If no city is mentioned, ask which city they mean instead of guessing.\n"
        "If the tool returns status 'success', answer naturally and briefly: "
        "describe the conditions in plain words (translate the WMO weather_code, "
        "e.g. 0 = clear sky, 3 = overcast, 61 = light rain), and mention the "
        "temperature, how it feels, humidity and wind with their units.\n"
        "If the tool returns status 'error', explain the problem to the user in "
        "plain language using error_message, and do not invent weather data."
    ),
    tools=[get_weather],
)
