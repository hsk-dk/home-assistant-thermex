# Thermex API Custom Component

This custom component integrates Thermex extractor hoods into Home Assistant, providing control over lighting, fan speed, and monitoring filter usage.

---

## Installation

Install through [HACS](https://hacs.xyz/) by adding this repository as a custom repository and selecting the integration type.

---

## Features

- Fan and light control
- Filter usage monitoring with customizable alerts
- Setup of Decolight controls (if supported by the hood)

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

- Set up the integration through the Home Assistant UI.
- Enter your extractor hood IP and password.
- Configure filter cleaning intervals.
- Enable Decolight via integration options (if needed).

---

## Compatibility

- Tested with Home Assistant version **2025.1.0** or later
- Thermex API version **1.1**

---

## Multi-language Support

- English
- Danish

---
