"""Weather lookup tool backed by the free Open-Meteo APIs (no API key needed)."""

from datetime import date, datetime
import math
import unicodedata
from typing import Literal
from urllib.parse import urlsplit

import requests

from .security import normalize_location, validate_location, validate_user_message

GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
ALLOWED_PROVIDER_HOSTS = frozenset(
    {"geocoding-api.open-meteo.com", "api.open-meteo.com"}
)
REQUEST_TIMEOUT_SECONDS = 10
CURRENT_VARIABLES = (
    "temperature_2m,apparent_temperature,relative_humidity_2m,weather_code,wind_speed_10m"
)
CURRENT_FIELDS = (
    "time",
    "temperature_2m",
    "apparent_temperature",
    "relative_humidity_2m",
    "weather_code",
    "wind_speed_10m",
)
DAILY_FIELDS = (
    "temperature_2m_max",
    "temperature_2m_min",
    "weather_code",
)
CURRENT_UNIT_OPTIONS = {
    "time": {"iso8601"},
    "temperature_2m": {"°C", "°F"},
    "apparent_temperature": {"°C", "°F"},
    "relative_humidity_2m": {"%"},
    "weather_code": {"wmo code"},
    "wind_speed_10m": {"km/h", "mph", "m/s", "kn"},
}
DAILY_UNIT_OPTIONS = {
    "temperature_2m_max": {"°C", "°F"},
    "temperature_2m_min": {"°C", "°F"},
    "weather_code": {"wmo code"},
}
MAX_CITY_LENGTH = 100
PLACE_NAME_PUNCTUATION = " -'.,"
SERVICE_UNAVAILABLE = "Could not reach the weather service. Please try again later."


def get_weather(city: str, day: Literal["today", "tomorrow"] = "today") -> dict:
    """Retrieves current or tomorrow's weather for a city.

    Args:
        city: Only the name of the city, e.g. "London" or "Tokyo". Letters,
            spaces, hyphens, apostrophes, periods and commas; max 100 characters.
        day: "today" for current conditions or "tomorrow" for the daily forecast.

    Returns:
        A dict with a "status" key. On "success" it also contains "location"
        (name, country), "current" (temperature_2m, apparent_temperature,
        relative_humidity_2m, weather_code as a WMO code, wind_speed_10m, time)
        for today, or "forecast" (date, daily high/low and WMO code) for
        tomorrow, with "units" for those values. On "error" it contains
        "error_message".
    """
    if not isinstance(city, str):
        return _error("Please provide a city name.")
    name = normalize_location(city)
    if not name:
        return _error("Please provide a city name.")
    if len(name) > MAX_CITY_LENGTH:
        return _error("That city name is too long. Please give just the city name.")
    if not _looks_like_place_name(name):
        return _error("That doesn't look like a city name. Please give just the city name.")
    if day not in ("today", "tomorrow"):
        return _error("Please choose today or tomorrow.")

    try:
        place = _geocode(name)
        if place is None:
            return _error(f"Could not find a city named '{city}'.")
        forecast = _fetch_weather(place["latitude"], place["longitude"])
    except requests.RequestException:
        return _error(SERVICE_UNAVAILABLE)

    result: dict = {
        "status": "success",
        "location": {
            "name": _clean_api_text(place["name"]) or name,
            "country": _clean_api_text(place.get("country")),
        },
    }
    if day == "tomorrow":
        parsed_daily = _parse_daily_forecast(forecast)
        if parsed_daily is None:
            return _error(SERVICE_UNAVAILABLE)
        result["forecast"], result["units"] = parsed_daily
        return result

    parsed_current = _parse_current_forecast(forecast)
    if parsed_current is None:
        return _error(SERVICE_UNAVAILABLE)
    result["current"], result["units"] = parsed_current
    return result


def _geocode(city: str) -> dict | None:
    """Returns the best Open-Meteo geocoding match for a city, or None."""
    payload = _request_json(
        GEOCODING_URL,
        params={"name": city, "count": 1},
    )
    results = payload.get("results")
    if results is None or results == []:
        return None
    if not isinstance(results, list):
        raise requests.RequestException("Invalid geocoding response.")
    place = results[0]
    if (
        not isinstance(place, dict)
        or not isinstance(place.get("name"), str)
        or not place["name"].strip()
        or (place.get("country") is not None and not isinstance(place["country"], str))
        or not _is_number(place.get("latitude"), -90, 90)
        or not _is_number(place.get("longitude"), -180, 180)
    ):
        raise requests.RequestException("Invalid geocoding response.")
    return place


def _fetch_weather(latitude: float, longitude: float) -> dict:
    """Returns the Open-Meteo payload for current and daily forecast data."""
    return _request_json(
        FORECAST_URL,
        params={
            "latitude": latitude,
            "longitude": longitude,
            "current": CURRENT_VARIABLES,
            "daily": ",".join(DAILY_FIELDS),
            "timezone": "auto",
            "forecast_days": 2,
        },
    )


def _request_json(url: str, *, params: dict) -> dict:
    _validate_provider_url(url)
    response = requests.get(
        url,
        params=params,
        timeout=REQUEST_TIMEOUT_SECONDS,
        allow_redirects=False,
    )
    _validate_provider_url(getattr(response, "url", url))
    if 300 <= response.status_code < 400:
        raise requests.HTTPError("Unexpected redirect from weather provider.")
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        raise requests.RequestException("Invalid weather response.")
    return payload


def _validate_provider_url(url: str) -> None:
    try:
        parsed = urlsplit(url)
        port = parsed.port
    except ValueError as error:
        raise requests.exceptions.InvalidURL(
            "Weather provider URL is not allowed."
        ) from error
    if (
        parsed.scheme != "https"
        or parsed.hostname not in ALLOWED_PROVIDER_HOSTS
        or parsed.username is not None
        or parsed.password is not None
        or port is not None
    ):
        raise requests.exceptions.InvalidURL("Weather provider URL is not allowed.")


def _looks_like_place_name(text: str) -> bool:
    """True if text uses only letters (any script), marks, and name punctuation."""
    return all(unicodedata.category(ch)[0] in "LM" or ch in PLACE_NAME_PUNCTUATION for ch in text)


def _clean_api_text(text: str | None) -> str | None:
    """Keep only short API location text that passes the user-name rules."""
    if text is None:
        return None
    printable = "".join(ch if ch.isprintable() else " " for ch in text)
    cleaned = " ".join(printable.split())[:MAX_CITY_LENGTH]
    try:
        validate_user_message(cleaned)
        return validate_location(cleaned)
    except ValueError:
        return None


def _select_fields(payload: dict, fields: tuple[str, ...]) -> dict:
    return {field: payload[field] for field in fields if field in payload}


def _parse_current_forecast(forecast: dict) -> tuple[dict, dict] | None:
    current = forecast.get("current")
    units = forecast.get("current_units")
    if not isinstance(current, dict) or not isinstance(units, dict):
        return None
    try:
        if not isinstance(current["time"], str):
            return None
        datetime.fromisoformat(current["time"])
        if not _is_number(current["temperature_2m"], -100, 70):
            return None
        if not _is_number(current["apparent_temperature"], -120, 80):
            return None
        if (
            not isinstance(current["relative_humidity_2m"], int)
            or isinstance(current["relative_humidity_2m"], bool)
            or not 0 <= current["relative_humidity_2m"] <= 100
        ):
            return None
        if (
            not isinstance(current["weather_code"], int)
            or isinstance(current["weather_code"], bool)
            or not 0 <= current["weather_code"] <= 99
        ):
            return None
        if not _is_number(current["wind_speed_10m"], 0, 500):
            return None
        if not _units_are_allowed(units, CURRENT_UNIT_OPTIONS):
            return None
    except (KeyError, ValueError):
        return None
    return _select_fields(current, CURRENT_FIELDS), _select_fields(units, CURRENT_FIELDS)


def _parse_daily_forecast(forecast: dict) -> tuple[dict, dict] | None:
    daily = forecast.get("daily")
    units = forecast.get("daily_units")
    if not isinstance(daily, dict) or not isinstance(units, dict):
        return None
    try:
        dates = daily["time"]
        highs = daily["temperature_2m_max"]
        lows = daily["temperature_2m_min"]
        codes = daily["weather_code"]
        if not all(
            isinstance(values, list) and len(values) >= 2
            for values in (dates, highs, lows, codes)
        ):
            return None
        forecast_date = dates[1]
        if not isinstance(forecast_date, str):
            return None
        date.fromisoformat(forecast_date)
        if not _is_number(highs[1], -100, 70) or not _is_number(lows[1], -100, 70):
            return None
        if lows[1] > highs[1]:
            return None
        if (
            not isinstance(codes[1], int)
            or isinstance(codes[1], bool)
            or not 0 <= codes[1] <= 99
            or not _units_are_allowed(units, DAILY_UNIT_OPTIONS)
        ):
            return None
    except (KeyError, IndexError, TypeError, ValueError):
        return None
    return (
        {
            "date": forecast_date,
            "temperature_2m_max": highs[1],
            "temperature_2m_min": lows[1],
            "weather_code": codes[1],
        },
        _select_fields(units, ("temperature_2m_max", "temperature_2m_min")),
    )


def _is_number(value: object, minimum: float, maximum: float) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and minimum <= value <= maximum
        and math.isfinite(value)
    )


def _units_are_allowed(units: dict, options: dict[str, set[str]]) -> bool:
    return all(
        isinstance(units.get(field), str) and units[field] in allowed
        for field, allowed in options.items()
    )


def _error(message: str) -> dict:
    return {"status": "error", "error_message": message}
