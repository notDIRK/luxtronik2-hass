"""Constants for the Luxtronik 2 Modbus Proxy integration."""

DOMAIN = "luxtronik2_modbus_proxy"

# Default connection parameters
DEFAULT_PORT = 8889
DEFAULT_POLL_INTERVAL = 30  # seconds

# Device identification
MANUFACTURER = "Alpha Innotec / Novelan"
MODEL = "Luxtronik 2.0"

# Write rate limiting — protects Luxtronik controller NAND flash (CTRL-04, D-05)
WRITE_RATE_LIMIT_SECONDS = 60
