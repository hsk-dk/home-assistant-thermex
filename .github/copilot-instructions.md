# Thermex Hood Integration - AI Coding Agent Guide

## Project Overview

This is a **Home Assistant custom integration** for Thermex extractor hoods with Voicelink API. The integration uses **WebSocket communication** for real-time control and monitoring.

### Core Architecture

**Hub-Based Design** ([hub.py](custom_components/thermex_api/hub.py))
- `ThermexHub`: Central WebSocket connection manager with automatic reconnection and watchdog monitoring
- Uses persistent connection with heartbeat messages (30s interval, 120s timeout)
- All platform entities communicate through the hub - never create direct connections
- Hub maintains connection state and dispatches updates via `THERMEX_NOTIFY` signal

**State Management Pattern**
- [__init__.py](custom_components/thermex_api/__init__.py): Entry point that initializes hub → RuntimeManager → DataUpdateCoordinator → platforms
- `RuntimeManager` ([runtime_manager.py](custom_components/thermex_api/runtime_manager.py)): Persistent storage for filter runtime tracking using Home Assistant's Store API
- Coordinator polls hub every 30 seconds; entities also subscribe to real-time notify signals via `async_dispatcher_connect(THERMEX_NOTIFY)`

**Platform Entities** ([fan.py](custom_components/thermex_api/fan.py), [light.py](custom_components/thermex_api/light.py), [sensor.py](custom_components/thermex_api/sensor.py))
- Each platform implements `async_setup_entry()` to create entities from hub reference
- All entities use `_attr_translation_key` and `_attr_has_entity_name = True` for translations
- Fan uses discrete preset modes (`off`, `low`, `medium`, `high`, `boost`) - avoid percentage-based speed
- Lights support brightness 0-255 with special handling for "turn off" vs "brightness 0"

## Development Workflows

### Running Tests

```powershell
# Install dependencies
pip install -r requirements_test.txt

# Run all tests
pytest

# Run with coverage
pytest --cov=custom_components.thermex_api --cov-report=html

# Run specific test file
pytest tests/test_runtime_manager.py

# Run specific test
pytest tests/test_runtime_manager.py::TestRuntimeManager::test_load_empty_store
```

### Test Patterns ([conftest.py](tests/conftest.py))

- Use shared fixtures: `mock_hub`, `mock_store`, `mock_hass`, `mock_config_entry`
- All async tests require `@pytest.mark.asyncio` decorator
- Mock hub includes `send_request` (AsyncMock) and `get_coordinator_data` (MagicMock)
- Tests validate state updates through notify signals, not just direct calls

### Critical Testing Requirements

1. **Always test notify signal handling** - entities update via dispatcher, not just coordinator refresh
2. **Test connection state transitions** - hub can be `connected`, `connecting`, `disconnected`
3. **Validate storage persistence** - RuntimeManager must handle corrupted data gracefully
4. **Test delayed operations** - fan delayed turn-off uses `async_call_later`, ensure cleanup in tests

## Project-Specific Conventions

### WebSocket Protocol (Thermex ESP API v1.0)

**Connection Details:**
- Endpoint: `ws://{host}:9999/api`
- Protocol: WebSocket with JSON request/response/notify objects
- Must enable API in Thermex mobile app before use
- Port: 9999 (TCP)

**Authentication Flow:**
First command after connection must be authentication:
```json
{
  "Request": "Authenticate",
  "Data": { "Code": "PASSWORD" }
}
```
Response: `{"Response": "Authenticate", "Status": 200}`

**API Commands:**
```python
# Status - Request complete device state
await hub.send_request("Status", {})

# Update - Control device (lowercase keys in Data)
await hub.send_request("Update", {
    "fan": {"fanonoff": 1, "fanspeed": 3},
    "light": {"lightonoff": 1, "lightbrightness": 100}
})

# ProtocolVersion - Query API version
await hub.send_request("ProtocolVersion", {})
```

**Data Object Specifications:**
- **light**: `lightonoff` (0-1), `lightbrightness` (1-100%)
- **fan**: `fanonoff` (0-1), `fanspeed` (1-4)
- **decolight**: `decolightonoff` (0-1), `decolightbrightness` (1-100%), `decolightr/g/b` (0-255)

**Response Format:**
```json
{
  "Response": "Status",
  "Status": 200,
  "Data": {
    "Light": {"lightonoff": 1, "lightbrightness": 100},
    "Fan": {"fanonoff": 1, "fanspeed": 3},
    "Decolight": {"decolightonoff": 1, "decolightr": 100, ...}
  }
}
```

**Status Codes:**
- 200: Success
- 400: Bad request format
- 401: Unauthorized (authentication failed)
- 500: Internal server error

**Notify Messages (Real-time Updates):**
Server sends unsolicited notify messages when state changes:
```json
{"Notify": "fan", "Data": {"Fan": {"fanonoff": 1, "fanspeed": 3}}}
{"Notify": "light", "Data": {"Light": {"lightonoff": 1, "lightbrightness": 100}}}
```
Hub dispatches these via `THERMEX_NOTIFY` signal to all entities.

**Implementation Notes:**
- Hub code uses `Motor` internally, mapped to API `fan` object
- Brightness ranges: API uses 1-100%, Home Assistant uses 0-255 (conversion required)
- Fan speed mapping: API 1-4 → presets: off=0, low=1, medium=2, high=3, boost=4
- Response keys are capitalized (Light/Fan/Decolight), request keys lowercase

**Critical Rules:**
- Never call `send_request` from entity constructors - only in async methods after `async_added_to_hass()`
- All requests must wait for response (uses futures pattern in hub.py)
- Connection errors trigger automatic reconnection via hub watchdog

### State Synchronization

**Two update paths:**
1. **Polling**: Coordinator calls `hub.get_coordinator_data()` every 30s
2. **Real-time**: Hub sends notify signals via `async_dispatcher_send(THERMEX_NOTIFY, notify_type, data)`

Both must be handled in entities:
```python
async def async_added_to_hass(self):
    self._unsub = async_dispatcher_connect(
        self.hass, THERMEX_NOTIFY, self._handle_notify
    )

async def _handle_notify(self, notify_type: str, data: dict):
    # Update state and call self.async_write_ha_state()
```

### RuntimeManager Integration

Filter tracking requires coordinated updates:
```python
# In fan.py - always update RuntimeManager before persisting
self._runtime_manager.start()  # When fan turns on
self._runtime_manager.stop()   # When fan turns off
await self._runtime_manager.save()  # Persist to storage
```

Storage file format: `thermex_api_{entry_id}_runtime.json` with validated float timestamps.

### Translation Structure

All user-facing strings use translation keys:
- Entity names: Set `_attr_translation_key = "thermex_fan"` and `_attr_has_entity_name = True`
- States: Preset modes automatically translated if defined in translations/*.json
- Options: Config flow options must have corresponding keys in `strings.json`

Check [translations/en.json](custom_components/thermex_api/translations/en.json) for required structure.

### Error Handling Patterns

**Connection Errors:**
```python
# Hub handles reconnection automatically - don't add retry logic in entities
try:
    await self._hub.send_request("Status", {})
except Exception as err:
    _LOGGER.error("Failed to get status: %s", err)
    # Entity should update to unavailable state
```

**Storage Validation:**
```python
# RuntimeManager validates all loaded data types
if not isinstance(data, dict):
    _LOGGER.warning("Corrupted data, starting fresh")
    self._data = {}
```

## Integration Points

### Home Assistant Services ([services.yaml](custom_components/thermex_api/services.yaml))

Registered in platform setup:
```python
# In fan.py async_setup_entry
platform = entity_platform.async_get_current_platform()
platform.async_register_entity_service("reset_runtime", {}, "async_reset")
```

Service calls are entity methods - implement as async member functions.

### Config Flow ([config_flow.py](custom_components/thermex_api/config_flow.py))

- `ConfigFlow.async_step_user`: Initial setup validates connection by creating temporary hub
- `OptionsFlowHandler.async_step_init`: Runtime options with vol.Range validators
- Errors use translation keys: `{"base": "cannot_connect"}` maps to strings.json

### Entry Lifecycle

```python
# Setup order in __init__.py - NEVER change this sequence
1. Create hub and connect
2. Initialize RuntimeManager and load storage
3. Create coordinator and do first refresh
4. Forward to platforms (light, fan, sensor, binary_sensor, button)
5. Register options update listener
```

Unload must reverse order and cleanup hub resources.

## Common Pitfalls

1. **Don't create multiple hub connections** - always use `hass.data[DOMAIN][entry.entry_id]["hub"]`
2. **Fan speed is NOT percentage** - use preset modes only, never `turn_on(percentage=50)`
3. **Light brightness 0 ≠ turn_off** - explicitly check command type in light entity
4. **Avoid blocking I/O** - all hub communication is async, never use `time.sleep()` or blocking calls
5. **Test async cleanup** - entities must unsubscribe from notify signals in `async_will_remove_from_hass()`
6. **Storage corruption handling** - RuntimeManager must handle invalid data types gracefully
7. **Watchdog interference** - hub has automatic reconnection, don't add competing retry logic

## Key Files Reference

- [hub.py](custom_components/thermex_api/hub.py): WebSocket manager (518 lines) - reference for connection patterns
- [runtime_manager.py](custom_components/thermex_api/runtime_manager.py): Persistent state example
- [fan.py](custom_components/thermex_api/fan.py): Complex entity with delayed operations (368 lines)
- [conftest.py](tests/conftest.py): Test fixtures and mocking patterns
- [const.py](custom_components/thermex_api/const.py): All timeouts and configuration constants
