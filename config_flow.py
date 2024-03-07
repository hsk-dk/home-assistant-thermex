from homeassistant import config_entries
from .thermex_api import ThermexApi
from .const import DOMAIN
import voluptuous as vol

class ThermexConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    async def async_step_user(self, user_input=None):
        if user_input is not None:
            host = user_input['host']
            code = user_input['code']
            
            # Initialize Thermex API
            thermex_api = ThermexApi(host, code)
            await thermex_api.connect()
            
            # Authenticate with Thermex API
            authenticated = await thermex_api.authenticate()
            if authenticated:
                # Retrieve information from API such as device ID, name, etc.
                #device_info = await thermex_api.get_device_info()
                unique_id = f"thermex_{host}"#device_info['device_id']
                name = "Thermix"#device_info['name']
                
                # Close the connection
                await thermex_api.close()

                # Create entry and set unique_id
                await self.async_set_unique_id(unique_id)
                self._abort_if_unique_id_configured()

                self.context["title_placeholders"] = {"unique_id": unique_id}

                # Create entry with device name and data
                return self.async_create_entry(title=name, data=user_input)
            else:
                return self.async_show_form(
                    step_id="user",
                    errors={"base": "Authentication failed. Please check your credentials."},
                )

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({
                vol.Required('host'): str,
                vol.Required('code'): str,
            })
        )
