# Thermex API Integration Tests

This directory contains comprehensive tests for the Thermex API Home Assistant custom integration.

## Test Structure

```
tests/
├── __init__.py                   # Test package initialization
├── conftest.py                   # Shared pytest fixtures
├── test_runtime_manager.py       # RuntimeManager unit tests
├── test_config_flow.py           # Configuration flow tests
├── test_fan.py                   # Fan entity tests
└── test_light.py                 # Light entity tests
```

## Running Tests

### Install Test Dependencies

```bash
pip install -r requirements_test.txt
```

### Run All Tests

```bash
pytest
```

### Run Specific Test File

```bash
pytest tests/test_runtime_manager.py
```

### Run with Coverage Report

```bash
pytest --cov=custom_components.thermex_api --cov-report=html
```

View coverage report: `htmlcov/index.html`

### Run Specific Test

```bash
pytest tests/test_runtime_manager.py::TestRuntimeManager::test_load_empty_store
```

## Test Coverage

Current test coverage includes:

### RuntimeManager (test_runtime_manager.py)
- ✅ Loading from empty store
- ✅ Loading existing data
- ✅ Data validation (negative runtime, invalid timestamps)
- ✅ Session start/stop
- ✅ Runtime accumulation with active sessions
- ✅ Runtime reset
- ✅ Days since reset calculation
- ✅ Multiple session handling
- ✅ Data persistence

### Config Flow (test_config_flow.py)
- ✅ User configuration form
- ✅ Valid input handling
- ✅ Connection error handling
- ✅ Options flow
- ✅ Input validation and ranges

### Fan Entity (test_fan.py)
- ✅ Entity initialization
- ✅ Preset modes
- ✅ Turn on/off operations
- ✅ Preset mode changes
- ✅ Notification handling
- ✅ State attributes
- ✅ Runtime reset service
- ✅ Delayed turn-off functionality

### Light Entities (test_light.py)
- ✅ ThermexLight initialization
- ✅ Brightness control
- ✅ Turn on/off operations
- ✅ Brightness clamping
- ✅ Notification handling
- ✅ ThermexDecoLight with RGB/HS color
- ✅ Color mode support

## Fixtures

Common fixtures available in `conftest.py`:

- `mock_hub` - Mocked ThermexHub instance
- `mock_store` - Mocked Home Assistant Store
- `mock_hass` - Mocked HomeAssistant instance
- `mock_config_entry` - Mocked ConfigEntry

## CI/CD Integration

Tests run automatically via GitHub Actions:

- **tests.yml** - Runs pytest on every push/PR
- **coverage.yml** - Generates coverage reports and comments on PRs

## Writing New Tests

### Example Test Structure

```python
import pytest
from unittest.mock import AsyncMock, MagicMock

class TestYourComponent:
    """Test your component."""

    @pytest.fixture
    def your_fixture(self, mock_hub):
        """Create test fixture."""
        return YourComponent(mock_hub)

    @pytest.mark.asyncio
    async def test_something(self, your_fixture):
        """Test something specific."""
        result = await your_fixture.do_something()
        assert result == expected_value
```

### Best Practices

1. **Use descriptive test names** - Name clearly describes what is tested
2. **One assertion per test** - Makes failures easier to diagnose
3. **Use fixtures** - Reuse common setup code
4. **Mock external dependencies** - Hub, store, network calls
5. **Test edge cases** - Invalid input, errors, boundary conditions
6. **Async tests** - Use `@pytest.mark.asyncio` decorator

## Coverage Goals

Target coverage: **≥80%**
- Unit tests: All core business logic
- Integration tests: Entity platforms and flows
- Edge cases: Error handling, validation

## Troubleshooting

### Import Errors

If you see import errors, ensure:
- You're in the project root directory
- Test dependencies are installed
- Python path includes the project

### Async Test Issues

Ensure async tests have:
```python
@pytest.mark.asyncio
async def test_async_function(self):
    ...
```

### Mock Issues

Use appropriate mock types:
- `MagicMock()` - Synchronous code
- `AsyncMock()` - Async functions
- `patch()` - Temporarily replace objects

## Future Test Additions

Planned test coverage expansions:
- [ ] Binary sensor tests
- [ ] Button entity tests  
- [ ] Sensor entity tests
- [ ] Diagnostics tests
- [ ] Hub WebSocket communication tests
- [ ] Integration tests with real data flows
