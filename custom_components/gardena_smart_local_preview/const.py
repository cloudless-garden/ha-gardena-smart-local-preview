# SPDX-FileCopyrightText: 2026 GARDENA GmbH
#
# SPDX-License-Identifier: Apache-2.0

DOMAIN = "gardena_smart_local_preview"

DEFAULT_PORT = 8443
DEFAULT_VALVE_DURATION_MINUTES = 30
DEFAULT_POWER_DURATION_MINUTES = 30

# Subentry data key holding {str(valve_id): minutes} for a device's valves
CONF_VALVE_DURATIONS = "valve_durations"
# Subentry data key holding a power outlet's default timed-on duration, in minutes
CONF_POWER_DURATION = "power_duration"
