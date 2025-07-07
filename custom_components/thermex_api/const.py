STARTUP = """
-------------------------------------------------------------------
Thermex Hood API integration

Version: %s
This is a custom integration
If you have any issues with this you need to open an issue here:
https://github.com/hsk-dk/home-assistant-thermex/issues
-------------------------------------------------------------------
"""
DOMAIN = "thermex_api"
DEFAULT_PORT = 9999
WEBSOCKET_PATH = "/api"
# Signal for dispatching notify messages
THERMEX_NOTIFY = "thermex_api_notify"
STORAGE_VERSION = 1
STORAGE_KEY = f"{DOMAIN}_runtime"
RUNTIME_STORAGE_FILE = f"{DOMAIN}_{{entry_id}}_runtime.json"