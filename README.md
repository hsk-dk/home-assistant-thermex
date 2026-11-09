[![home-assistant-thermex](https://img.shields.io/github/v/release/hsk-dk/home-assistant-thermex?display_name=release&style=plastic&labelColor=green)](https://github.com/hsk-dk/home-assistant-thermex) [![hacs_badge](https://img.shields.io/badge/HACS-Default-41BDF5.svg?style=plastic)](https://github.com/hacs/integration) [![downloads](https://img.shields.io/github/downloads/hsk-dk/home-assistant-thermex/total?style=plastic&label=Total%20downloads)](https://github.com/hsk-dk/home-assistant-thermex) [![Buy me a coffee](https://img.shields.io/static/v1?label=Buy%20me%20a%20coffee&message=and%20say%20thanks&color=orange&logo=buymeacoffee&logoColor=white&style=plastic)](https://www.buymeacoffee.com/hskdk)

# Thermex Hood Integration Custom Component

This custom component integrates Thermex extractor hoods into Home Assistant, providing comprehensive control over lighting, fan speed, filter monitoring, and advanced automation features.

---

## Installation
[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=hsk-dk&repository=home-assistant-thermex)

Install through the Home Assistant **Marketplace** (Settings → Marketplace, Home Assistant 2026.11 and newer) by searching for "Thermex Hood Integration". On earlier versions, use [HACS](https://hacs.xyz/) the same way.

---

## Features

### Core Functionality
- **Fan Control**: Full speed control with preset modes (Low, Medium, High, Boost)
- **Light Control**: Main hood lighting and Decolight control (if supported)
- **Filter Monitoring**: Real-time filter usage tracking with customizable alerts
- **Connection Monitoring**: Real-time connection status with automatic reconnection

### Advanced Features
- **Delayed Turn-Off**: Manual activation of delayed fan turn-off with configurable timer (1-120 minutes)
- **Runtime Tracking**: Persistent filter runtime tracking with reset functionality
- **Dual Filter Alerts**: Monitor both runtime hours (default: 30h) and days since reset (default: 90 days)
- **Automatic Reconnection**: Built-in watchdog monitors connection and automatically reconnects on failures
- **Real-time Updates**: Push notifications for all state changes via WebSocket
- **Diagnostic Support**: Built-in diagnostics for troubleshooting (Settings → Devices → Thermex Hood → Download Diagnostics)
- **Multi-language Support**: Full localisation in English, Danish, Swedish, Norwegian, Finnish, German and Spanish

### Entities Created
- **Fan Entity**: `fan.thermex_hood` with speed presets and runtime attributes
- **Light Entities**: Main light and Decolight (if enabled)
- **Sensors**: 
  - Grease filter runtime hours, and hours until the next cleaning (counts down from the alert threshold)
  - Connection status (diagnostic, disabled by default)
  - Last reset time, and days since it
  - Delayed turn-off timer status
- **Binary Sensor**: Filter cleaning alert (hours and days thresholds)
- **Buttons**: 
  - Reset filter time
  - Start delayed turn-off

### Services Available
- `thermex_api.reset_runtime`: Reset filter runtime counter (also available as button entity)
- `thermex_api.start_delayed_off`: Start delayed turn-off timer (also available as button entity). The optional `minutes` (1-120) sets the delay for this one run; without it the configured delay is used
- `thermex_api.cancel_delayed_off`: Cancel active delayed turn-off

All three actions target the Thermex fan entity. `start_delayed_off` returns an error if the fan is not running.

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

### Adding the integration

1. Go to Settings → Devices & Services → Add Integration → **Thermex Hood**.
2. Enter your extractor hood IP address and API password, and tick **Activate Ambient light** if your model has the Decolight (it can be changed later under Configure). If Home Assistant sees the hood on your network (it announces itself as `Thermex-ESP`), it is offered automatically under **Discovered**, and only the API password is needed.
3. Optionally change the options later under **Configure** on the integration entry:
   - **Activate Ambient light**: turns the Decolight controls on (if your model supports it)
   - **Grease filter cleaning notice after (runtime hours)**: 1-1000 hours (default: 30)
   - **Grease filter cleaning notice after (days since reset)**: 1-365 days (default: 90)
   - **Delayed turn-off timer (minutes)**: 1-120 minutes (default: 10)

### Changing the IP address or password

If the hood gets a new IP address (or you change the API password in the Thermex app), use
**Settings → Devices & Services → Thermex Hood → ⋮ → Reconfigure**. Entities, history and
automations are kept: they are identified by an internal ID, not by the IP address. If the hood
rejects the stored password, Home Assistant also offers a re-authentication prompt.

A hood that was found by discovery is recognised by its MAC address, so a new IP address handed out by
your router is picked up automatically (the integration reloads with the new address). A hood added
by hand learns its MAC address the first time Home Assistant sees it on the network. Discovery relies
on the DHCP messages Home Assistant can see, so it needs Home Assistant to be on the same network as
the hood; if it is not offered, add the hood manually.


---

## Compatibility

- **Home Assistant**: Version **2025.8.0** or later
- **Thermex API**: Version **1.1** (WebSocket protocol)

## Known Supported Models

- Thermex hoods with [Voicelink](https://thermex.eu/advice-and-guidance/all-options/voicelink) technology
- Minimum software version: **1.30/1.10**

## Troubleshooting

### Common Issues

1. **Connection failed when adding the hood**:
   - Verify the hood IP address and the API password
   - Check that the API is enabled in the Thermex app
   - Check that Home Assistant can reach the hood on port 9999 (same network or routed)
   - Check that the hood software is at least version 1.30/1.10
2. **Entities unavailable or connection drops**:
   - Entities become unavailable while the hood is offline and recover automatically; the integration reconnects by itself
   - A hood that loses power or drops off the network without closing the connection is detected by the connection watchdog, marked unavailable and reconnected (v3.4.0-rc2 and later)
   - The *Connection status* sensor (diagnostic, disabled by default) shows the state and why the last connection was lost
   - Set the log level to debug (see below) and check the Home Assistant log for details
3. **Filter alert not working**:
   - Check the hours and days limits in the integration options
   - Runtime is only counted while the fan runs
   - The alert triggers when EITHER the hours OR the days limit is exceeded
   - Use the reset button or the `thermex_api.reset_runtime` action after you have cleaned the filter

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
- **Code Validation**: Ruff (must pass), mypy (advisory), Hassfest and HACS validation

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

This integration is maintained in my spare time and tested on my own hood. If it is useful to you, a coffee is a nice way to say thanks. Bug reports and test results are just as welcome.

[![Buy me a coffee](https://img.shields.io/static/v1?label=Buy%20me%20a%20coffee&message=and%20say%20thanks&color=orange&logo=buymeacoffee&logoColor=white&style=plastic)](https://www.buymeacoffee.com/hskdk)
