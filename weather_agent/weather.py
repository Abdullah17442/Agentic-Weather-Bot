"""Weather lookup tool backed by the free Open-Meteo APIs (no API key needed)."""

import requests

GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
REQUEST_TIMEOUT_SECONDS = 10
CURRENT_VARIABLES = (
    "temperature_2m,apparent_temperature,relative_humidity_2m,weather_code,wind_speed_10m"
)
SERVICE_UNAVAILABLE = "Could not reach the weather service. Please try again later."


def get_weather(city: str) -> dict:
    """Retrieves the current weather for a city.

    Args:
        city: The name of the city, e.g. "London" or "Tokyo".

    Returns:
        A dict with a "status" key. On "success" it also contains "location"
        (name, country), "current" (temperature_2m, apparent_temperature,
        relative_humidity_2m, weather_code as a WMO code, wind_speed_10m, time)
        and "units" for those values. On "error" it contains "error_message".
    """
    if not city.strip():
        return _error("Please provide a city name.")

    try:
        place = _geocode(city.strip())
        if place is None:
            return _error(f"Could not find a city named '{city}'.")
        forecast = _fetch_current_weather(place["latitude"], place["longitude"])
    except requests.RequestException:
        return _error(SERVICE_UNAVAILABLE)

    return {
        "status": "success",
        "location": {"name": place["name"], "country": place.get("country")},
        "current": forecast["current"],
        "units": forecast["current_units"],
    }


def _geocode(city: str) -> dict | None:
    """Returns the best Open-Meteo geocoding match for a city, or None."""
    response = requests.get(
        GEOCODING_URL,
        params={"name": city, "count": 1},
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    results = response.json().get("results")
    return results[0] if results else None


def _fetch_current_weather(latitude: float, longitude: float) -> dict:
    """Returns the Open-Meteo forecast payload with current conditions."""
    response = requests.get(
        FORECAST_URL,
        params={
            "latitude": latitude,
            "longitude": longitude,
            "current": CURRENT_VARIABLES,
            "timezone": "auto",
        },
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    return response.json()


def _error(message: str) -> dict:
    return {"status": "error", "error_message": message}
