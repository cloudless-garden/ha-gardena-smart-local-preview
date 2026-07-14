# SPDX-FileCopyrightText: 2026 GARDENA GmbH
#
# SPDX-License-Identifier: Apache-2.0

"""Tests for the GARDENA smart local config flow."""

from __future__ import annotations

from ipaddress import ip_address
from unittest.mock import AsyncMock, MagicMock, patch

import aiohttp
import pytest
from homeassistant.config_entries import SOURCE_IMPORT, SOURCE_USER, SOURCE_ZEROCONF
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_PORT
from homeassistant.core import HomeAssistant
from homeassistant.helpers.service_info.zeroconf import ZeroconfServiceInfo
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.gardena_smart_local_preview.const import DEFAULT_PORT, DOMAIN
from custom_components.gardena_smart_local_preview.coordinator import (
    IncludableDeviceInfo,
)

MOCK_HOST = "192.168.1.100"
MOCK_PORT = DEFAULT_PORT
MOCK_PASSWORD = "testpassword"

PATCH_TRY_CONNECT = (
    "custom_components.gardena_smart_local_preview.config_flow._async_try_connect"
)
PATCH_SETUP_ENTRY = "custom_components.gardena_smart_local_preview.async_setup_entry"
PATCH_UNLOAD_ENTRY = "custom_components.gardena_smart_local_preview.async_unload_entry"


@pytest.fixture
def mock_setup_entry():
    """Prevent actual integration setup during config flow tests."""
    with patch(PATCH_SETUP_ENTRY, return_value=True):
        yield


def _make_zeroconf_info(
    hostname: str = "gardena-gw-1234.local.",
    host: str = MOCK_HOST,
    port: int = MOCK_PORT,
) -> ZeroconfServiceInfo:
    return ZeroconfServiceInfo(
        ip_address=ip_address(host),
        ip_addresses=[ip_address(host)],
        hostname=hostname,
        name=f"{hostname.removesuffix('.')}._gardena-smart._tcp.local.",
        port=port,
        properties={},
        type="_gardena-smart._tcp.local.",
    )


# ---------------------------------------------------------------------------
# User flow
# ---------------------------------------------------------------------------


async def test_user_flow_success(hass: HomeAssistant, mock_setup_entry) -> None:
    """Happy path: manual entry creates a config entry."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    assert result["type"] == "form"
    assert result["step_id"] == "user"

    with patch(PATCH_TRY_CONNECT, return_value=None):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_HOST: MOCK_HOST, CONF_PORT: MOCK_PORT, CONF_PASSWORD: MOCK_PASSWORD},
        )

    assert result["type"] == "create_entry"
    assert result["data"] == {
        CONF_HOST: MOCK_HOST,
        CONF_PORT: MOCK_PORT,
        CONF_PASSWORD: MOCK_PASSWORD,
    }


async def test_user_flow_cannot_connect(hass: HomeAssistant) -> None:
    """Connection failure shows an error and keeps the form open."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )

    with patch(
        "aiohttp.ClientSession.ws_connect",
        side_effect=aiohttp.ClientConnectionError("Connection failed"),
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_HOST: MOCK_HOST, CONF_PORT: MOCK_PORT, CONF_PASSWORD: MOCK_PASSWORD},
        )

    assert result["type"] == "form"
    assert result["errors"] == {"base": "cannot_connect"}


async def test_user_flow_invalid_auth(hass: HomeAssistant) -> None:
    """Wrong password (HTTP 401) shows invalid_auth error."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )

    with patch(
        "aiohttp.ClientSession.ws_connect",
        side_effect=aiohttp.WSServerHandshakeError(
            request_info=MagicMock(),
            history=(),
            status=401,
            message="Unauthorized",
        ),
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_HOST: MOCK_HOST, CONF_PORT: MOCK_PORT, CONF_PASSWORD: MOCK_PASSWORD},
        )

    assert result["type"] == "form"
    assert result["errors"] == {"base": "invalid_auth"}


async def test_user_flow_unknown_error(hass: HomeAssistant) -> None:
    """Unexpected exception shows generic unknown error."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )

    with patch(
        "aiohttp.ClientSession.ws_connect",
        side_effect=RuntimeError("Unexpected error"),
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_HOST: MOCK_HOST, CONF_PORT: MOCK_PORT, CONF_PASSWORD: MOCK_PASSWORD},
        )

    assert result["type"] == "form"
    assert result["errors"] == {"base": "unknown"}


async def test_user_flow_already_configured(hass: HomeAssistant) -> None:
    """Duplicate gateway is rejected with already_configured abort."""
    MockConfigEntry(
        domain=DOMAIN,
        unique_id=MOCK_HOST,
        data={CONF_HOST: MOCK_HOST, CONF_PORT: MOCK_PORT, CONF_PASSWORD: MOCK_PASSWORD},
    ).add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )

    with patch(PATCH_TRY_CONNECT, return_value=None):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_HOST: MOCK_HOST, CONF_PORT: MOCK_PORT, CONF_PASSWORD: MOCK_PASSWORD},
        )

    assert result["type"] == "abort"
    assert result["reason"] == "already_configured"


# ---------------------------------------------------------------------------
# Zeroconf discovery flow
# ---------------------------------------------------------------------------


async def test_zeroconf_discovery_and_confirm(
    hass: HomeAssistant, mock_setup_entry
) -> None:
    """Zeroconf discovery shows a confirmation form, then creates the entry."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": SOURCE_ZEROCONF},
        data=_make_zeroconf_info(),
    )
    assert result["type"] == "form"
    assert result["step_id"] == "discovery_confirm"

    with patch(PATCH_TRY_CONNECT, return_value=None):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_HOST: MOCK_HOST, CONF_PORT: MOCK_PORT, CONF_PASSWORD: MOCK_PASSWORD},
        )

    assert result["type"] == "create_entry"
    assert result["data"][CONF_HOST] == MOCK_HOST
    assert result["data"][CONF_PORT] == MOCK_PORT


async def test_zeroconf_already_configured(hass: HomeAssistant) -> None:
    """Zeroconf discovery aborts when the gateway is already set up."""
    MockConfigEntry(
        domain=DOMAIN,
        unique_id="gardena-gw-1234",
        data={CONF_HOST: MOCK_HOST, CONF_PORT: MOCK_PORT, CONF_PASSWORD: MOCK_PASSWORD},
    ).add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": SOURCE_ZEROCONF},
        data=_make_zeroconf_info(),
    )
    assert result["type"] == "abort"
    assert result["reason"] == "already_configured"


async def test_zeroconf_confirm_cannot_connect(hass: HomeAssistant) -> None:
    """Failed connection at zeroconf confirmation shows an error."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": SOURCE_ZEROCONF},
        data=_make_zeroconf_info(),
    )
    assert result["type"] == "form"

    with patch(
        "aiohttp.ClientSession.ws_connect",
        side_effect=aiohttp.ClientConnectionError("Connection failed"),
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_HOST: MOCK_HOST, CONF_PORT: MOCK_PORT, CONF_PASSWORD: MOCK_PASSWORD},
        )

    assert result["type"] == "form"
    assert result["errors"] == {"base": "cannot_connect"}


# ---------------------------------------------------------------------------
# Reconfigure flow
# ---------------------------------------------------------------------------


async def test_reconfigure_success(hass: HomeAssistant, mock_setup_entry) -> None:
    """Successful reconfiguration updates entry data."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=MOCK_HOST,
        data={CONF_HOST: MOCK_HOST, CONF_PORT: MOCK_PORT, CONF_PASSWORD: MOCK_PASSWORD},
    )
    entry.add_to_hass(hass)

    result = await entry.start_reconfigure_flow(hass)
    assert result["type"] == "form"
    assert result["step_id"] == "reconfigure"

    new_host = "192.168.1.200"
    with patch(PATCH_TRY_CONNECT, return_value=None):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_HOST: new_host, CONF_PORT: MOCK_PORT, CONF_PASSWORD: MOCK_PASSWORD},
        )

    assert result["type"] == "abort"
    assert result["reason"] == "reconfigure_successful"
    assert entry.data[CONF_HOST] == new_host


async def test_reconfigure_cannot_connect(hass: HomeAssistant) -> None:
    """Failed connection during reconfigure keeps the form open."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=MOCK_HOST,
        data={CONF_HOST: MOCK_HOST, CONF_PORT: MOCK_PORT, CONF_PASSWORD: MOCK_PASSWORD},
    )
    entry.add_to_hass(hass)

    result = await entry.start_reconfigure_flow(hass)

    with patch(
        "aiohttp.ClientSession.ws_connect",
        side_effect=aiohttp.ClientConnectionError("Connection failed"),
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_HOST: "192.168.1.200",
                CONF_PORT: MOCK_PORT,
                CONF_PASSWORD: MOCK_PASSWORD,
            },
        )

    assert result["type"] == "form"
    assert result["errors"] == {"base": "cannot_connect"}


# ---------------------------------------------------------------------------
# Reauthentication flow
# ---------------------------------------------------------------------------


async def test_reauth_success(hass: HomeAssistant, mock_setup_entry) -> None:
    """Successful reauthentication updates the stored password."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=MOCK_HOST,
        data={CONF_HOST: MOCK_HOST, CONF_PORT: MOCK_PORT, CONF_PASSWORD: "old-pw"},
    )
    entry.add_to_hass(hass)

    result = await entry.start_reauth_flow(hass)
    assert result["type"] == "form"
    assert result["step_id"] == "reauth_confirm"

    with patch(PATCH_TRY_CONNECT, return_value=None):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_PASSWORD: MOCK_PASSWORD}
        )

    assert result["type"] == "abort"
    assert result["reason"] == "reauth_successful"
    assert entry.data[CONF_PASSWORD] == MOCK_PASSWORD
    assert entry.data[CONF_HOST] == MOCK_HOST


async def test_reauth_invalid_auth(hass: HomeAssistant) -> None:
    """Wrong password during reauth keeps the form open with an error."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=MOCK_HOST,
        data={CONF_HOST: MOCK_HOST, CONF_PORT: MOCK_PORT, CONF_PASSWORD: "old-pw"},
    )
    entry.add_to_hass(hass)

    result = await entry.start_reauth_flow(hass)

    with patch(
        "aiohttp.ClientSession.ws_connect",
        side_effect=aiohttp.WSServerHandshakeError(
            request_info=MagicMock(),
            history=(),
            status=401,
            message="Unauthorized",
        ),
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_PASSWORD: "still-wrong"}
        )

    assert result["type"] == "form"
    assert result["step_id"] == "reauth_confirm"
    assert result["errors"] == {"base": "invalid_auth"}
    assert entry.data[CONF_PASSWORD] == "old-pw"


# ---------------------------------------------------------------------------
# Import flow (YAML)
# ---------------------------------------------------------------------------


async def test_import_flow_success(hass: HomeAssistant, mock_setup_entry) -> None:
    """YAML import creates an entry without a connection test."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": SOURCE_IMPORT},
        data={CONF_HOST: MOCK_HOST, CONF_PORT: MOCK_PORT, CONF_PASSWORD: MOCK_PASSWORD},
    )
    assert result["type"] == "create_entry"
    assert result["data"][CONF_HOST] == MOCK_HOST


async def test_import_flow_already_configured(hass: HomeAssistant) -> None:
    """YAML import aborts if the gateway is already configured."""
    MockConfigEntry(
        domain=DOMAIN,
        unique_id=MOCK_HOST,
        data={CONF_HOST: MOCK_HOST, CONF_PORT: MOCK_PORT, CONF_PASSWORD: MOCK_PASSWORD},
    ).add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": SOURCE_IMPORT},
        data={CONF_HOST: MOCK_HOST, CONF_PORT: MOCK_PORT, CONF_PASSWORD: MOCK_PASSWORD},
    )
    assert result["type"] == "abort"
    assert result["reason"] == "already_configured"


# ---------------------------------------------------------------------------
# Device inclusion subentry flow
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_coordinator():
    coordinator = MagicMock()
    coordinator.includable_devices = {}
    coordinator.async_include_device = AsyncMock(return_value=None)
    return coordinator


async def test_inclusion_subentry_no_devices(
    hass: HomeAssistant, mock_coordinator
) -> None:
    """Subentry flow aborts when no includable devices are advertising."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=MOCK_HOST,
        data={CONF_HOST: MOCK_HOST, CONF_PORT: MOCK_PORT, CONF_PASSWORD: MOCK_PASSWORD},
    )
    entry.add_to_hass(hass)
    entry.runtime_data = mock_coordinator

    result = await hass.config_entries.subentries.async_init(
        (entry.entry_id, "device"),
        context={"source": "user"},
    )
    assert result["type"] == "form"
    assert result["step_id"] == "user"

    # Proceed past the intro form
    result = await hass.config_entries.subentries.async_configure(result["flow_id"], {})
    assert result["type"] == "abort"
    assert result["reason"] == "no_devices_found"


async def test_inclusion_subentry_success(
    hass: HomeAssistant, mock_coordinator
) -> None:
    """Subentry flow creates a subentry when inclusion succeeds."""
    instance_id = "instance-abc"
    device_id = "device-xyz"
    mock_coordinator.includable_devices = {
        instance_id: IncludableDeviceInfo(
            instance_id=instance_id,
            service="some-service",
            device_id=device_id,
            device_name="GARDENA Device 001",
        )
    }
    mock_coordinator.async_include_device = AsyncMock(return_value=device_id)
    mock_coordinator.data = {}

    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=MOCK_HOST,
        data={CONF_HOST: MOCK_HOST, CONF_PORT: MOCK_PORT, CONF_PASSWORD: MOCK_PASSWORD},
    )
    entry.add_to_hass(hass)
    entry.runtime_data = mock_coordinator

    result = await hass.config_entries.subentries.async_init(
        (entry.entry_id, "device"),
        context={"source": "user"},
    )
    # Past intro
    result = await hass.config_entries.subentries.async_configure(result["flow_id"], {})
    assert result["type"] == "form"
    assert result["step_id"] == "select"

    # Select the device
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"], {"device": instance_id}
    )
    assert result["type"] == "create_entry"
    assert result["data"]["device_id"] == device_id


async def test_inclusion_subentry_failed(hass: HomeAssistant, mock_coordinator) -> None:
    """Subentry flow shows an error when the gateway rejects inclusion."""
    instance_id = "instance-abc"
    mock_coordinator.includable_devices = {
        instance_id: IncludableDeviceInfo(
            instance_id=instance_id,
            service="some-service",
            device_id="device-xyz",
            device_name="GARDENA Device 001",
        )
    }
    mock_coordinator.async_include_device = AsyncMock(return_value=None)

    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=MOCK_HOST,
        data={CONF_HOST: MOCK_HOST, CONF_PORT: MOCK_PORT, CONF_PASSWORD: MOCK_PASSWORD},
    )
    entry.add_to_hass(hass)
    entry.runtime_data = mock_coordinator

    result = await hass.config_entries.subentries.async_init(
        (entry.entry_id, "device"),
        context={"source": "user"},
    )
    result = await hass.config_entries.subentries.async_configure(result["flow_id"], {})
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"], {"device": instance_id}
    )
    assert result["type"] == "form"
    assert result["errors"] == {"base": "inclusion_failed"}
