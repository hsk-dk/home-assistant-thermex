# Thermex API Custom Component

This custom component integrates Thermex extractor hoods into Home Assistant, providing control over lighting, fan speed, and monitoring filter usage.

## Installation

Install through HACS by adding this repository as a custom repository and selecting the integration type.

## Features
- Fan and light control.
- Filter usage monitoring with customizable alerts.
- Setup up of Decolight controls if supported by the hood.

## Configuration

 - A Thermex extractor hood supporting voicelink is needed (https://thermex.eu/advice-and-guidance/all-options/voicelink)

 - Setup API
   1) Check software version, minimum version is 1.30/1.10
![Screenshot_app_0](https://github.com/user-attachments/assets/d5a0f1ad-e006-4d50-9a16-9d79af83f132)
   2)Enable API and set password in native phone app from Thermex
![Screenshot_app_1](https://github.com/user-attachments/assets/c80412a1-1f13-4f23-b347-01a2cd9c2202)
![Screenshot_app_2](https://github.com/user-attachments/assets/2bc877bb-490f-4272-afdf-2f059b35dd1c)


 Set up integration through the Home Assistant UI. Enter your extractor hood IP and password. Configure filter cleaning intervals, and enable decolight if needed via integration options.

## Compatibility
- Tested with Home Assistant version 2025.1.0 or later.
- Themex API version 1.1

### Multi-language Support
- English and Danish language supported.


