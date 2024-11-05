quick guide:
1) enable API and set password in native phone app from Thermex
2) Download the latest release for the component.
3) Unpack the release and copy the custom_components/thermex directory into the custom_components directory of your Home Assistant installation.
4) Setup i configuiration.yaml by adding: 
   <code>thermex_api:
   host: x.x.x.x {IP address of hood}
   password: {password set in app}</code>
5) restart home-assistant

if everything works 2 services, a sensor and a light entity have been added to home-assistant.
