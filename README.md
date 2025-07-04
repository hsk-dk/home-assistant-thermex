Quick guide:
A Thermex extractor hood supporting voicelink is needed (https://thermex.eu/advice-and-guidance/all-options/voicelink)

Setup API
1) Check software version, minimum version is 1.30/1.10
![Screenshot_app_0](https://github.com/user-attachments/assets/d5a0f1ad-e006-4d50-9a16-9d79af83f132)
2)Enable API and set password in native phone app from Thermex
![Screenshot_app_1](https://github.com/user-attachments/assets/c80412a1-1f13-4f23-b347-01a2cd9c2202)
![Screenshot_app_2](https://github.com/user-attachments/assets/2bc877bb-490f-4272-afdf-2f059b35dd1c)

Setup Home-Assistant
1) Download the latest release for the component.
2) Unpack the release and copy the custom_components/thermex directory into the custom_components directory of your Home Assistant installation.
3) Setup i configuiration.yaml by adding: 
   <code>thermex_api:
   host: "x.x.x.x" {IP address of hood}
   password:"password" {password set in app}</code>
4) restart home-assistant

if everything works 2 actions, a sensor, a light entity and a switch have been added to home-assistant.
2 Actions:
 - Thermex (api): update_fan
 - Thermex (api): update_light
Choose YAML mode for help.
1 sensor:
 - sensor.thermex_fan_sensor - showing the status of the hood
1 lighy
 - light.thermex_light - control of the hood light
1 switch
 - switch.thermex_fan_switch - on/off switch for the hood (use actions to control speed) 


## Installation via HACS

1. Go to HACS → Integrations → Custom Repositories.
2. Add your repository: `https://github.com/hsk-dk/home-assistant-thermex`
3. Select Integration as the category.
4. Install the integration.
5. Restart Home Assistant.
6. Go to Settings → Devices & Services → Add Integration and search for “Thermex”.

## Example

Configuration is handled through the UI config flow. No YAML required.

## Support

Please file issues at: [GitHub Issues](https://github.com/hsk-dk/home-assistant-thermex/issues)