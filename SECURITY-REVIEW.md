# Security Fix Report

## Summary

The weather agent had a prompt-injection risk in its error handling. When a city
was not found, the weather tool copied the complete user-supplied city string
into `error_message`. That result is returned to the language model, so
instruction-like text submitted as a city could be mistaken for trusted tool
output.

## Finding

| Severity | Component | Issue | Status |
|---|---|---|---|
| Medium | `weather_agent/weather.py` | Raw user input was echoed into a model-visible error message. | Fixed |

## Fixes Applied

1. Added a fixed `CITY_NOT_FOUND` message that does not contain user input.
2. Added a regression test proving injection text is not echoed in not-found
   errors.
3. Corrected the configured model in `weather_agent/agent.py` from
   `gemini-3.5-flash-lite` to the tested `gemini-3.6-flash` model.
4. Normalized the spacing around the weather service error constant.

## Validation

The complete test suite passes:

```text
27 passed, 1 warning
```

The warning comes from third-party pytest plugins and is unrelated to these
changes.

## Remaining Safety Controls

- City input is restricted to place-name characters and a maximum length.
- The agent has only the read-only `get_weather` tool.
- Tool output is explicitly treated as data rather than instructions.
- Requests to override the agent's role or reveal its instructions are refused.
