"""Constantes pour l'intégration FastIron."""
DOMAIN = "fastiron"

DEFAULT_PORT = 443
DEFAULT_SCAN_INTERVAL = 60
DEFAULT_VERIFY_SSL = False

CONF_VERIFY_SSL = "verify_ssl"
CONF_SCAN_INTERVAL = "scan_interval"
CONF_ENABLE_DIAGNOSTIC_SENSORS = "enable_diagnostic_sensors"

DEFAULT_ENABLE_DIAGNOSTIC_SENSORS = False

# Clés stockées dans entry.data lors du config flow
ENTRY_SW_MODEL = "sw_model"
ENTRY_SW_FIRMWARE = "sw_firmware"
ENTRY_SW_HOSTNAME = "sw_hostname"
