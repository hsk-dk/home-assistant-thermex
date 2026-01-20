[![home-assistant-thermex](https://img.shields.io/github/v/release/hsk-dk/home-assistant-thermex?display_name=release&style=plastic&labelColor=green)](https://github.com/hsk-dk/home-assistant-thermex) [![hacs_badge](https://img.shields.io/badge/HACS-Default-41BDF5.svg?style=plastic)](https://github.com/hacs/integration) [![downloads](https://img.shields.io/github/downloads/hsk-dk/home-assistant-thermex/total?style=plastic&label=Total%20downloads)](https://github.com/hsk-dk/home-assistant-thermex) 

<a href="https://www.buymeacoffee.com/hskdk" target="_blank"><img src="https://www.buymeacoffee.com/assets/img/custom_images/orange_img.png" alt="Buy Me A Coffee" style="height: 41px !important;width: 174px !important;box-shadow: 0px 3px 2px 0px rgba(190, 190, 190, 0.5) !important;-webkit-box-shadow: 0px 3px 2px 0px rgba(190, 190, 190, 0.5) !important;" ></a>

# Thermex Hood Integration Custom Component

This custom component integrates Thermex extractor hoods into Home Assistant, providing comprehensive control over lighting, fan speed, filter monitoring, and advanced automation features.

---

## Installation
[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=hsk-dk&repository=home-assistant-thermex)

Install through [HACS](https://hacs.xyz/) by searching for "Thermex Hood Integration".

---

## Features

### Core Functionality
- **Fan Control**: Full speed control with preset modes (Off, Low, Medium, High, Boost)
- **Light Control**: Main hood lighting and Decolight control (if supported)
- **Filter Monitoring**: Real-time filter usage tracking with customizable alerts
- **Connection Monitoring**: Real-time connection status with automatic reconnection

### Advanced Features
- **Delayed Turn-Off**: Manual activation of delayed fan turn-off with configurable timer (1-120 minutes)
- **Runtime Tracking**: Persistent filter runtime tracking with reset functionality
- **Diagnostic Sensors**: Connection status, protocol version, and system health monitoring
- **Multi-language Support**: Full localisation in English, Danish, Swedish, Norwegian, Finnish and German

### Entities Created
- **Fan Entity**: `fan.thermex_hood` with speed presets and runtime attributes
- **Light Entities**: Main light and Decolight (if enabled)
- **Sensors**: Filter runtime, connection status, last reset time
- **Binary Sensor**: Filter cleaning alert
- **Buttons**: Reset filter time, Start delayed turn-off

### Services Available
- `thermex_api.reset_runtime`: Reset filter runtime counter
- `thermex_api.start_delayed_off`: Start delayed turn-off timer
- `thermex_api.cancel_delayed_off`: Cancel active delayed turn-off

---

## Configuration

### Prerequisites

- A Thermex extractor hood supporting [voicelink](https://thermex.eu/advice-and-guidance/all-options/voicelink)

### API Setup

1. Check software version (minimum required: 1.30/1.10):

   ![Check software version](https://github.com/user-attachments/assets/d5a0f1ad-e006-4d50-9a16-9d79af83f132)

2. Enable API and set a password in the official Thermex phone app:

   ![Enable API](https://github.com/user-attachments/assets/c80412a1-1f13-4f23-b347-01a2cd9c2202)
   ![Set password](https://github.com/user-attachments/assets/2bc877bb-490f-4272-afdf-2f059b35dd1c)

### Integration Setup

1. Set up the integration through the Home Assistant UI
2. Enter your extractor hood IP address and API password
3. Configure integration options:
   - **Filter Alert Hours**: Set filter cleaning interval (default: 30 hours)
   - **Enable Decolight**: Activate ambient lighting controls (if supported)
   - **Delayed Turn-Off Timer**: Configure automatic turn-off delay (1-120 minutes, default: 10)


---

## Compatibility

- **Home Assistant**: Version **2025.1.0** or later
- **Thermex API**: Version **1.1**

## Known Supported Models

- Thermex hoods with [Voicelink](https://thermex.eu/advice-and-guidance/all-options/voicelink) technology
- Minimum software version: **1.30/1.10**

## Troubleshooting

### Common Issues

1. **Connection Failed**: 
   - Verify hood IP address and API password
   - Check network connectivity
   - Ensure API is enabled in Thermex app

2. **No Initial Status**: 
   - Integration includes a connection watchdog for automatic recovery
   - Check hood software version (minimum 1.30/1.10 required)

3. **Filter Alerts Not Working**:
   - Verify filter alert hours are configured in integration options
   - Check that runtime tracking is active (fan has been used)

### Debug Information

Enable debug logging by adding this to your `configuration.yaml`:
```yaml
logger:
  logs:
    custom_components.thermex_api: debug
```

---

## Development

### Running Tests

This integration includes a comprehensive test suite with unit and integration tests.

#### Install Test Dependencies
```bash
pip install -r requirements_test.txt
```

#### Run Tests
```bash
# Run all tests
pytest

# Run with coverage report
pytest --cov --cov-report=html

# Run specific test file
pytest tests/test_runtime_manager.py
```

See [tests/README.md](tests/README.md) for detailed testing documentation.

### CI/CD

The project uses GitHub Actions for automated testing:
- **Tests**: Run on every push and PR
- **Coverage**: Automatic coverage reports on PRs
- **Code Validation**: Ruff and mypy checks

---

## Contributing

Issues and feature requests are welcome! Please use the [GitHub Issues](https://github.com/hsk-dk/home-assistant-thermex/issues) page.

### Development Workflows

This repository uses automated workflows for release management:

- **📖 [Complete Workflows Guide](WORKFLOWS_GUIDE.md)** - Detailed documentation for developers and maintainers
- **🚀 [Quick Reference](WORKFLOWS_QUICKREF.md)** - Quick lookup for common tasks

#### For Contributors
1. Use proper branch naming: `feature/new-sensor`, `fix/bug-description`
2. Label your PRs appropriately for automatic release notes
3. Follow semantic commit messages: `feat:`, `fix:`, `docs:`, `chore:`

#### For Maintainers
- **Creating Releases**: Use the automated workflows in GitHub Actions
- **Release Notes**: Automatically generated from PR labels
- **Pre-releases**: Available for testing new features

See the [workflows documentation](WORKFLOWS_GUIDE.md) for complete details on labeling, branching, and release processes.

## Support

[![Buy me a coffee](https://img.shields.io/static/v1?label=Buy%20me%20a%20coffee&message=and%20say%20thanks&color=orange&logo=buymeacoffee&logoColor=white&style=plastic)](https://www.buymeacoffee.com/hskdk)
