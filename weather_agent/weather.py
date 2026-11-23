"""Weather lookup tool backed by OpenWeather or the free Open-Meteo fallback."""

import os
import unicodedata
from datetime import datetime, timezone

import requests

GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
OPENWEATHER_URL = "https://api.openweathermap.org/data/2.5/weather"
REQUEST_TIMEOUT_SECONDS = 10
CURRENT_VARIABLES = (
    "temperature_2m,apparent_temperature,relative_humidity_2m,weather_code,wind_speed_10m"
)
MAX_CITY_LENGTH = 100
PLACE_NAME_PUNCTUATION = " -'.,"
SERVICE_UNAVAILABLE = "Could not reach the weather service. Please try again later."
CITY_NOT_FOUND = "Could not find a matching city. Please check the spelling and try again."


def get_weather(city: str) -> dict:
    """Retrieves the current weather for a city.

    Args:
        city: Only the name of the city, e.g. "London" or "Tokyo". Letters,
            spaces, hyphens, apostrophes, periods and commas; max 100 characters.

    Returns:
        A dict with a "status" key. On "success" it also contains "location"
        (name, country), "current" (temperature_2m, apparent_temperature,
        relative_humidity_2m, weather_code as a WMO code, wind_speed_10m, time)
        and "units" for those values. On "error" it contains "error_message".
    """
    name = city.strip()
    if not name:
        return _error("Please provide a city name.")
    if len(name) > MAX_CITY_LENGTH:
        return _error("That city name is too long. Please give just the city name.")
    if not _looks_like_place_name(name):
        return _error("That doesn't look like a city name. Please give just the city name.")

    api_key = os.getenv("OPENWEATHER_API_KEY", "").strip()
    if api_key:
        try:
            return _fetch_openweather(name, api_key)
        except requests.HTTPError as exc:
            if getattr(exc.response, "status_code", None) == 404:
                return _error(CITY_NOT_FOUND)
            return _error(SERVICE_UNAVAILABLE)
        except requests.RequestException:
            return _error(SERVICE_UNAVAILABLE)

    try:
        place = _geocode(name)
        if place is None:
            return _error(CITY_NOT_FOUND)
        forecast = _fetch_current_weather(place["latitude"], place["longitude"])
    except requests.RequestException:
        return _error(SERVICE_UNAVAILABLE)

    return {
        "status": "success",
        "location": {
            "name": _clean_api_text(place["name"]),
            "country": _clean_api_text(place.get("country")),
        },
        "current": forecast["current"],
        "units": forecast["current_units"],
    }


def _fetch_openweather(city: str, api_key: str) -> dict:
    """Fetch and normalize a current-weather response from OpenWeather."""
    response = requests.get(
        OPENWEATHER_URL,
        params={"q": city, "appid": api_key, "units": "metric"},
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    try:
        response.raise_for_status()
    except requests.HTTPError as exc:
        exc.response = response
        raise
    payload = response.json()

    main = payload.get("main") or {}
    wind = payload.get("wind") or {}
    weather_items = payload.get("weather") or []
    weather = weather_items[0] if weather_items else {}
    timestamp = payload.get("dt")
    time_text = None
    if isinstance(timestamp, (int, float)):
        time_text = datetime.fromtimestamp(timestamp, tz=timezone.utc).isoformat()

    location = payload.get("name") or city
    country = (payload.get("sys") or {}).get("country")
    weather_description = weather.get("description")
    weather_id = weather.get("id")

    return {
        "status": "success",
        "location": {
            "name": _clean_api_text(location),
            "country": _clean_api_text(country),
        },
        "current": {
            "time": time_text,
            "temperature_2m": main.get("temp"),
            "apparent_temperature": main.get("feels_like"),
            "relative_humidity_2m": main.get("humidity"),
            "weather_code": weather_id,
            "weather_description": weather_description,
            "wind_speed_10m": wind.get("speed"),
        },
        "units": {
            "time": "iso8601",
            "temperature_2m": "°C",
            "apparent_temperature": "°C",
            "relative_humidity_2m": "%",
            "weather_code": "openweather id",
            "weather_description": "text",
            "wind_speed_10m": "m/s",
        },
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


def _looks_like_place_name(text: str) -> bool:
    """True if text uses only letters (any script), marks, and name punctuation."""
    return all(
        unicodedata.category(ch)[0] in "LM" or ch in PLACE_NAME_PUNCTUATION
        for ch in text
    )


def _clean_api_text(text: str | None) -> str | None:
    """Flatten external text to one printable line, capped in length."""
    if text is None:
        return None
    printable = "".join(ch if ch.isprintable() else " " for ch in text)
    return " ".join(printable.split())[:MAX_CITY_LENGTH]


def _error(message: str) -> dict:
    return {"status": "error", "error_message": message}
