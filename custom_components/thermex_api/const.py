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

# Connection and Watchdog settings
DEFAULT_HEARTBEAT_INTERVAL = 30  # Seconds between heartbeat status requests
DEFAULT_CONNECTION_TIMEOUT = 120  # Seconds before connection considered dead
DEFAULT_RECONNECT_DELAY = 2  # Seconds between reconnection attempts
MAX_RECONNECT_ATTEMPTS = 3  # Maximum number of consecutive reconnection attempts
RECONNECT_WAIT_ITERATIONS = 20  # Wait iterations for another task's reconnection
WEBSOCKET_REQUEST_TIMEOUT = 10  # Seconds to wait for websocket response

# Light settings
DEFAULT_BRIGHTNESS = 204  # Default brightness (80% of 255)
MIN_BRIGHTNESS = 0  # Minimum brightness value
MAX_BRIGHTNESS = 255  # Maximum brightness value
FALLBACK_STATUS_TIMEOUT = 15  # Seconds to wait before requesting fallback status