import pytest
import requests

from weather_agent.weather import get_weather


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code} error")


@pytest.fixture
def fake_http(monkeypatch):
    """Replace requests.get with a fake that answers by URL and records calls."""
    responses = {}  # URL substring -> FakeResponse
    calls = []

    def fake_get(url, **kwargs):
        calls.append({"url": url, **kwargs})
        for fragment, response in responses.items():
            if fragment in url:
                if isinstance(response, Exception):
                    raise response
                return response
        raise AssertionError(f"Unexpected URL requested: {url}")

    monkeypatch.setattr(requests, "get", fake_get)
    return responses, calls


@pytest.mark.parametrize("city", ["", "   "])
def test_returns_error_for_blank_city(city):
    result = get_weather(city)

    assert result["status"] == "error"
    assert "city" in result["error_message"].lower()


def test_returns_error_when_city_is_not_found(fake_http):
    responses, _ = fake_http
    responses["geocoding-api.open-meteo.com"] = FakeResponse({"generationtime_ms": 0.5})

    result = get_weather("Atlantisville")

    assert result["status"] == "error"
    assert "Atlantisville" in result["error_message"]


LONDON_GEOCODING = {
    "results": [
        {
            "name": "London",
            "country": "United Kingdom",
            "latitude": 51.50853,
            "longitude": -0.12574,
        }
    ]
}


LONDON_FORECAST = {
    "latitude": 51.5,
    "longitude": -0.120000124,
    "current_units": {
        "time": "iso8601",
        "interval": "seconds",
        "temperature_2m": "°C",
        "apparent_temperature": "°C",
        "relative_humidity_2m": "%",
        "weather_code": "wmo code",
        "wind_speed_10m": "km/h",
    },
    "current": {
        "time": "2026-11-18T23:00",
        "interval": 900,
        "temperature_2m": 8.4,
        "apparent_temperature": 6.1,
        "relative_humidity_2m": 87,
        "weather_code": 3,
        "wind_speed_10m": 11.2,
    },
}


@pytest.fixture
def london(fake_http):
    responses, calls = fake_http
    responses["geocoding-api.open-meteo.com"] = FakeResponse(LONDON_GEOCODING)
    responses["api.open-meteo.com/v1/forecast"] = FakeResponse(LONDON_FORECAST)
    return calls


def test_returns_current_weather_for_city_coordinates(london):
    result = get_weather("London")

    forecast_call = london[-1]
    assert forecast_call["params"]["latitude"] == 51.50853
    assert forecast_call["params"]["longitude"] == -0.12574
    assert result["current"]["temperature_2m"] == 8.4
    assert result["current"]["weather_code"] == 3
    assert result["units"]["temperature_2m"] == "°C"


def test_returns_resolved_location_for_known_city(london):
    result = get_weather("london")

    assert result["status"] == "success"
    assert result["location"] == {"name": "London", "country": "United Kingdom"}


def test_returns_error_when_weather_service_is_unreachable(london, fake_http):
    responses, _ = fake_http
    responses["api.open-meteo.com/v1/forecast"] = requests.ConnectionError("network down")

    result = get_weather("London")

    assert result["status"] == "error"
    assert "weather service" in result["error_message"].lower()


def test_returns_error_when_geocoding_service_is_unreachable(fake_http):
    responses, _ = fake_http
    responses["geocoding-api.open-meteo.com"] = requests.Timeout("timed out")

    result = get_weather("London")

    assert result["status"] == "error"
    assert "weather service" in result["error_message"].lower()


def test_returns_error_when_weather_service_responds_with_http_error(london, fake_http):
    responses, _ = fake_http
    responses["api.open-meteo.com/v1/forecast"] = FakeResponse(
        {"error": True, "reason": "Internal error"}, status_code=500
    )

    result = get_weather("London")

    assert result["status"] == "error"
    assert "weather service" in result["error_message"].lower()


def test_returns_error_when_geocoding_service_responds_with_http_error(fake_http):
    responses, _ = fake_http
    responses["geocoding-api.open-meteo.com"] = FakeResponse(
        {"error": True, "reason": "Rate limit exceeded"}, status_code=429
    )

    result = get_weather("London")

    assert result["status"] == "error"
    assert "weather service" in result["error_message"].lower()


def test_every_request_has_a_timeout_so_a_hung_service_cannot_block(london):
    get_weather("London")

    assert len(london) == 2
    for call in london:
        assert call.get("timeout"), f"No timeout on request to {call['url']}"


def test_returns_weather_for_place_without_a_country(fake_http):
    responses, _ = fake_http
    responses["geocoding-api.open-meteo.com"] = FakeResponse(
        {"results": [{"name": "McMurdo Station", "latitude": -77.85, "longitude": 166.67}]}
    )
    responses["api.open-meteo.com/v1/forecast"] = FakeResponse(LONDON_FORECAST)

    result = get_weather("McMurdo Station")

    assert result["status"] == "success"
    assert result["location"] == {"name": "McMurdo Station", "country": None}
