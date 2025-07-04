# Thermex API Custom Component

This custom component integrates Thermex extractor hoods into Home Assistant, providing control over lighting, fan speed, and monitoring filter usage.

## Installation

Install through HACS by adding this repository as a custom repository and selecting the integration type.

## Features
- Fan and light control.
- Filter usage monitoring with customizable alerts.

## Configuration

Set up integration through the Home Assistant UI. Enter your extractor hood IP and password. Configure filter cleaning intervals via integration options.

## Services
- `thermex_api.reset_filter_usage`: Reset the filter usage counter after cleaning.

## Compatibility
- Tested with Home Assistant version 2023.1.0 or later.


## Enhanced Diagnostics and UI

### Multi-language Support
- English and Danish language supported.

### Diagnostics
- Check the Thermex Diagnostic entity for troubleshooting connection or configuration issues.

### Lovelace UI Example
```yaml
type: entities
title: Thermex Extractor Hood
entities:
  - entity: switch.thermex_fan
    name: Fan
  - entity: light.thermex_light
    name: Light
  - entity: sensor.thermex_filter_usage
    name: Filter Usage (Hours)
  - entity: sensor.thermex_diagnostic
    name: Connection Status
  - type: button
    name: Reset Filter Timer
    icon: mdi:filter-remove
    tap_action:
      action: call-service
      service: thermex_api.reset_filter_usage
```
