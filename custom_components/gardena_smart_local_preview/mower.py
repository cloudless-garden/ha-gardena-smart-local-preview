# SPDX-FileCopyrightText: 2026 GARDENA GmbH
#
# SPDX-License-Identifier: Apache-2.0

"""Read-only helpers for Gen1 mower resources the library does not expose yet."""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta

from gardena_smart_local_api.devices import Gen1Mower1, Gen1Mower2
from gardena_smart_local_api.devices.device import Device
from gardena_smart_local_api.resources import IpsoPath

# Reported instead of an error name when there is nothing to report.
NO_MESSAGE = "no_message"

# Error code -> translation state (entity.sensor.last_error.state.*).
# The numbering is the Husqvarna Automower Connect API one, taken from the
# aioautomower library and keyed like Home Assistant's husqvarna_automower
# integration. GARDENA does not document the local codes; a real code 15
# matched a lift at the station on 23.09.2026. 0 means no error (see
# INFORMATIONAL_CODES); unknown codes are exposed as "code_<n>".
ERROR_CODES: dict[int, str] = {
    1: "outside_working_area",
    2: "no_loop_signal",
    3: "wrong_loop_signal",
    4: "loop_sensor_problem_front",
    5: "loop_sensor_problem_rear",
    6: "loop_sensor_problem_left",
    7: "loop_sensor_problem_right",
    8: "wrong_pin_code",
    9: "trapped",
    10: "upside_down",
    11: "low_battery",
    12: "empty_battery",
    13: "no_drive",
    14: "mower_lifted",
    15: "lifted",
    16: "stuck_in_charging_station",
    17: "charging_station_blocked",
    18: "collision_sensor_problem_rear",
    19: "collision_sensor_problem_front",
    20: "wheel_motor_blocked_right",
    21: "wheel_motor_blocked_left",
    22: "wheel_drive_problem_right",
    23: "wheel_drive_problem_left",
    24: "cutting_system_blocked",
    25: "cutting_system_blocked",
    26: "invalid_sub_device_combination",
    27: "settings_restored",
    28: "memory_circuit_problem",
    29: "slope_too_steep",
    30: "charging_system_problem",
    31: "stop_button_problem",
    32: "tilt_sensor_problem",
    33: "mower_tilted",
    34: "cutting_stopped_slope_too_steep",
    35: "wheel_motor_overloaded_right",
    36: "wheel_motor_overloaded_left",
    37: "charging_current_too_high",
    38: "electronic_problem",
    39: "cutting_motor_problem",
    40: "limited_cutting_height_range",
    41: "unexpected_cutting_height_adj",
    42: "limited_cutting_height_range",
    43: "cutting_height_problem_drive",
    44: "cutting_height_problem_curr",
    45: "cutting_height_problem_dir",
    46: "cutting_height_blocked",
    47: "cutting_height_problem",
    48: "no_response_from_charger",
    49: "ultrasonic_problem",
    50: "guide_1_not_found",
    51: "guide_2_not_found",
    52: "guide_3_not_found",
    53: "gps_navigation_problem",
    54: "weak_gps_signal",
    55: "difficult_finding_home",
    56: "guide_calibration_accomplished",
    57: "guide_calibration_failed",
    58: "temporary_battery_problem",
    59: "temporary_battery_problem",
    60: "temporary_battery_problem",
    61: "temporary_battery_problem",
    62: "battery_restriction_due_to_ambient_temperature",
    63: "temporary_battery_problem",
    64: "temporary_battery_problem",
    65: "temporary_battery_problem",
    66: "battery_problem",
    67: "battery_problem",
    68: "temporary_battery_problem",
    69: "alarm_mower_switched_off",
    70: "alarm_mower_stopped",
    71: "alarm_mower_lifted",
    72: "alarm_mower_tilted",
    73: "alarm_mower_in_motion",
    74: "alarm_outside_geofence",
    75: "connection_changed",
    76: "connection_not_changed",
    77: "com_board_not_available",
    78: "slipped_mower_has_slipped_situation_not_solved_with_moving_pattern",
    79: "invalid_battery_combination_invalid_combination_of_different_battery_types",
    80: "cutting_system_imbalance_warning",
    81: "safety_function_faulty",
    82: "wheel_motor_blocked_rear_right",
    83: "wheel_motor_blocked_rear_left",
    84: "wheel_drive_problem_rear_right",
    85: "wheel_drive_problem_rear_left",
    86: "wheel_motor_overloaded_rear_right",
    87: "wheel_motor_overloaded_rear_left",
    88: "angular_sensor_problem",
    89: "invalid_system_configuration",
    90: "no_power_in_charging_station",
    91: "switch_cord_problem",
    92: "work_area_not_valid",
    93: "no_accurate_position_from_satellites",
    94: "reference_station_communication_problem",
    95: "folding_sensor_activated",
    96: "right_brush_motor_overloaded",
    97: "left_brush_motor_overloaded",
    98: "ultrasonic_sensor_1_defect",
    99: "ultrasonic_sensor_2_defect",
    100: "ultrasonic_sensor_3_defect",
    101: "ultrasonic_sensor_4_defect",
    102: "cutting_drive_motor_1_defect",
    103: "cutting_drive_motor_2_defect",
    104: "cutting_drive_motor_3_defect",
    105: "lift_sensor_defect",
    106: "collision_sensor_defect",
    107: "docking_sensor_defect",
    108: "folding_cutting_deck_sensor_defect",
    109: "loop_sensor_defect",
    110: "collision_sensor_error",
    111: "no_confirmed_position",
    112: "cutting_system_major_imbalance",
    113: "complex_working_area",
    114: "too_high_discharge_current",
    115: "too_high_internal_current",
    116: "high_charging_power_loss",
    117: "high_internal_power_loss",
    118: "charging_system_problem",
    119: "zone_generator_problem",
    120: "internal_voltage_error",
    121: "high_internal_temperature",
    122: "can_error",
    123: "destination_not_reachable",
    124: "destination_blocked",
    125: "battery_needs_replacement",
    126: "battery_near_end_of_life",
    127: "battery_problem",
    128: "multiple_reference_stations_detected",
    129: "auxiliary_cutting_means_blocked",
    130: "imbalanced_auxiliary_cutting_disc_detected",
    131: "lifted_in_link_arm",
    132: "epos_accessory_missing",
    133: "bluetooth_communication_with_charging_station_failed",
    134: "invalid_software_configuration",
    135: "radar_problem",
    136: "work_area_tampered",
    137: "high_temperature_in_cutting_motor_right",
    138: "high_temperature_in_cutting_motor_center",
    139: "high_temperature_in_cutting_motor_left",
    141: "wheel_brush_motor_problem",
    142: "self_diagnostic_error",
    143: "accessory_power_problem",
    144: "boundary_wire_problem",
    145: "no_correction_data_available",
    147: "cutting_disc_lost",
    148: "chassis_collision",
    149: "vision_system_malfunction",
    151: "poor_vision_performance",
    152: "vision_system_error",
    153: "charging_aborted",
    154: "water_hose_found_in_working_area",
    155: "pin_code_changed",
    156: "wi_fi_settings_changed",
    157: "bluetooth_settings_changed",
    158: "cellular_settings_changed",
    159: "mower_installation_position_changed",
    160: "firmware_has_been_updated",
    161: "no_charging_station_signal",
    701: "connectivity_problem",
    702: "connectivity_settings_restored",
    703: "connectivity_problem",
    704: "connectivity_problem",
    705: "connectivity_problem",
    706: "poor_signal_quality",
    707: "sim_card_requires_pin",
    708: "sim_card_locked",
    709: "sim_card_not_found",
    710: "sim_card_locked",
    711: "sim_card_locked",
    712: "sim_card_locked",
    713: "geofence_problem",
    714: "geofence_problem",
    715: "connectivity_problem",
    716: "connectivity_problem",
    717: "sms_could_not_be_sent",
    724: "communication_circuit_board_sw_must_be_updated",
}

# Codes that do not describe a fault (0 = no error since the last reset).
INFORMATIONAL_CODES: frozenset[int] = frozenset({0})

_UTC_OFFSET_RE = re.compile(
    r"^UTC(?:(?P<sign>[+-])(?P<hours>\d{2}):(?P<minutes>\d{2}))?$"
)


def is_gen1_mower(device: object) -> bool:
    return isinstance(device, (Gen1Mower1, Gen1Mower2))


def _lemonbeat_path(resource_name: str) -> IpsoPath:
    return IpsoPath(
        object_name="lemonbeat", object_instance_id="0", resource_name=resource_name
    )


def get_lemonbeat_int(device: Device, resource_name: str) -> int | None:
    value = device.get_value(_lemonbeat_path(resource_name))
    return value if isinstance(value, int) else None


def get_last_error_code(device: Device) -> int | None:
    return get_lemonbeat_int(device, "last_error_code")


def parse_utc_offset(text: str | None) -> timedelta | None:
    """Parse the gateway's ``utc_offset`` string, e.g. ``UTC+02:00``."""
    if not isinstance(text, str):
        return None
    match = _UTC_OFFSET_RE.match(text)
    if match is None:
        return None
    if match.group("sign") is None:
        return timedelta(0)
    offset = timedelta(
        hours=int(match.group("hours")), minutes=int(match.group("minutes"))
    )
    return -offset if match.group("sign") == "-" else offset


def get_utc_offset(device: Device) -> timedelta:
    value = device.get_value(
        IpsoPath(
            object_name="device", object_instance_id="0", resource_name="utc_offset"
        )
    )
    return parse_utc_offset(value if isinstance(value, str) else None) or timedelta(0)


def _get_local_epoch(device: Device, resource_name: str) -> datetime | None:
    # The mower reports these as 4 bytes big-endian "seconds since 1970 in
    # local time", i.e. already shifted by the device's UTC offset. Undo the
    # shift so Home Assistant gets a real instant.
    value = device.get_value(_lemonbeat_path(resource_name))
    if not isinstance(value, bytes) or len(value) != 4:
        return None
    seconds = int.from_bytes(value, "big")
    if seconds == 0:
        return None
    return datetime.fromtimestamp(seconds, UTC) - get_utc_offset(device)


def get_last_error_timestamp(device: Device) -> datetime | None:
    return _get_local_epoch(device, "timestamp_last_error_code")


def error_code_to_state(code: int | None) -> str | None:
    if code is None:
        return None
    if code in INFORMATIONAL_CODES:
        return NO_MESSAGE
    return ERROR_CODES.get(code, f"code_{code}")


def get_current_error_codes(device: Device) -> list[int]:
    """Currently active error codes; 0 is the gateway's "no error" marker."""
    value = device.get_value(
        IpsoPath(
            object_name="device", object_instance_id="0", resource_name="error_code"
        )
    )
    if not isinstance(value, list):
        return []
    return [code for code in value if isinstance(code, int) and code != 0]
