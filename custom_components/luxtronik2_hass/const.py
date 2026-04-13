"""Constants for the Luxtronik 2.0 (Home Assistant) integration."""

DOMAIN = "luxtronik2_hass"

# Default connection parameters
DEFAULT_PORT = 8889
DEFAULT_POLL_INTERVAL = 30  # seconds

# Device identification
MANUFACTURER = "Alpha Innotec / Novelan"
MODEL = "Luxtronik 2.0"

# Write rate limiting — protects Luxtronik controller NAND flash (CTRL-04, D-05)
WRITE_RATE_LIMIT_SECONDS = 60

# Directory name (relative to HA config dir) for parameter backup JSON files.
BACKUP_DIR = "luxtronik2_backups"

# ---------------------------------------------------------------------------
# Smart Energy defaults
# ---------------------------------------------------------------------------

# Luxtronik parameter indices
PARAM_HOT_WATER_SETPOINT = 2       # ID_Einst_BWS_akt (the *setting*, not computed)
PARAM_HEATING_MODE = 3              # ID_Ba_Hz_akt
PARAM_HOT_WATER_MODE = 4            # ID_Ba_Bw_akt
PARAM_HOT_WATER_MAX = 973           # ID_Einst_BW_max (read-only, max allowed WW temp)

# Solar Boost defaults
DEFAULT_SOLAR_BOOST_ENABLED = False
DEFAULT_GRID_SENSOR = ""            # empty = feature disabled
DEFAULT_SOLAR_THRESHOLD = 1500      # watts — feed-in above this triggers boost
DEFAULT_SOLAR_NORMAL_TEMP = 55.5    # °C — normal hot water setpoint
DEFAULT_SOLAR_BOOST_TEMP = 65.0     # °C — boosted hot water setpoint
DEFAULT_SOLAR_MIN_RUNTIME = 30      # minutes — minimum time boost stays active
SOLAR_DEBOUNCE_SECONDS = 60         # Grid must stay below threshold for 60s before boost activates
DEFAULT_WW_HYSTERESIS = 5.0         # Kelvin — controller hysteresis for hot water heating start

# Night Heating Pause defaults
DEFAULT_NIGHT_PAUSE_ENABLED = False
DEFAULT_NIGHT_PAUSE_START = "18:00"
DEFAULT_NIGHT_PAUSE_END = "09:00"

# Bath Boost defaults
DEFAULT_BATH_BOOST_TARGET_TEMP = 65.0   # °C — target temperature for bath boost
DEFAULT_BATH_BOOST_NORMAL_TEMP = 55.5   # °C — restore after boost completes
DEFAULT_BATH_BOOST_HEAT_RATE = 4.0      # °C per hour — fallback estimation rate

# Hot water mode values (matches select.py MODE_OPTIONS)
HOT_WATER_MODE_AUTOMATIC = 0
HOT_WATER_MODE_PARTY = 2

# Heating mode values (matches select.py MODE_OPTIONS)
HEATING_MODE_AUTO = 0
HEATING_MODE_OFF = 4
