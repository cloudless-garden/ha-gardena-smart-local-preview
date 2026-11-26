# SPDX-FileCopyrightText: 2026 GARDENA GmbH
#
# SPDX-License-Identifier: Apache-2.0

"""Tests for the GARDENA smart local config flow."""

from __future__ import annotations

from ipaddress import ip_address
from unittest.mock import AsyncMock, MagicMock, patch

import aiohttp
import pytest
import voluptuous_serialize
from gardena_smart_local_api.client import AuthenticationError, ConfigApiError
from homeassistant.config_entries import (
    SOURCE_IMPORT,
    SOURCE_USER,
    SOURCE_ZEROCONF,
    ConfigFlowResult,
)
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_PORT
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType, InvalidData
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.service_info.zeroconf import ZeroconfServiceInfo
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.gardena_smart_local_preview.const import (
    CONF_CLOUD_CONNECTION,
    DEFAULT_PORT,
    DOMAIN,
)
from custom_components.gardena_smart_local_preview.coordinator import (
    IncludableDeviceInfo,
)

MOCK_HOST = "192.168.1.100"
MOCK_PORT = DEFAULT_PORT
MOCK_PASSWORD = "testpassword"

PATCH_TRY_CONNECT = (
    "custom_components.gardena_smart_local_preview.config_flow._async_try_connect"
)
PATCH_EXTRACT_HOSTNAME_FROM_CERT = "custom_components.gardena_smart_local_preview.config_flow.async_extract_hostname_from_cert"
PATCH_CONFIG_API = (
    "custom_components.gardena_smart_local_preview.config_flow.GatewayConfigApi"
)
PATCH_SETUP_ENTRY = "custom_components.gardena_smart_local_preview.async_setup_entry"
PATCH_UNLOAD_ENTRY = "custom_components.gardena_smart_local_preview.async_unload_entry"


@pytest.fixture
def mock_setup_entry():
    """Prevent actual integration setup during config flow tests."""
    with patch(PATCH_SETUP_ENTRY, return_value=True):
        yield


@pytest.fixture(autouse=True)
def mock_extract_hostname_from_cert():
    """Skip the TLS certificate probe unless a test opts in."""
    with patch(PATCH_EXTRACT_HOSTNAME_FROM_CERT, return_value=None) as mock:
        yield mock


@pytest.fixture(autouse=True)
def mock_config_api():
    """Skip the web interface of the gateway, which reports the cloud as on."""
    with patch(PATCH_CONFIG_API) as config_api_class:
        config_api = config_api_class.return_value
        config_api.get_cloud_connection = AsyncMock(return_value=True)
        config_api.set_cloud_connection = AsyncMock()
        yield config_api_class


@pytest.fixture
def mock_get_cloud_connection(mock_config_api) -> AsyncMock:
    return mock_config_api.return_value.get_cloud_connection


@pytest.fixture
def mock_set_cloud_connection(mock_config_api) -> AsyncMock:
    return mock_config_api.return_value.set_cloud_connection


def _make_zeroconf_info(
    hostname: str = "GARDENA-123456.local.",
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


async def test_user_flow_strips_host_whitespace(
    hass: HomeAssistant, mock_setup_entry
) -> None:
    """Leading/trailing whitespace in the host is stripped before use."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )

    with patch(PATCH_TRY_CONNECT, return_value=None) as try_connect:
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_HOST: f"  {MOCK_HOST}\t",
                CONF_PORT: MOCK_PORT,
                CONF_PASSWORD: MOCK_PASSWORD,
            },
        )

    assert result["type"] == "create_entry"
    assert result["data"][CONF_HOST] == MOCK_HOST
    assert try_connect.call_args[0][1] == MOCK_HOST


async def test_user_form_schema_serializes(hass: HomeAssistant) -> None:
    """The form schema must serialize, or the frontend gets a 500."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )

    fields = voluptuous_serialize.convert(
        result["data_schema"], custom_serializer=cv.custom_serializer
    )
    host = next(f for f in fields if f["name"] == CONF_HOST)
    assert host["strip"] is True


async def test_user_flow_uses_certificate_hostname(
    hass: HomeAssistant, mock_setup_entry, mock_extract_hostname_from_cert
) -> None:
    """The hostname from the TLS certificate becomes the unique_id."""
    mock_extract_hostname_from_cert.return_value = "GARDENA-123456"

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    with patch(PATCH_TRY_CONNECT, return_value=None):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_HOST: MOCK_HOST, CONF_PORT: MOCK_PORT, CONF_PASSWORD: MOCK_PASSWORD},
        )

    assert result["type"] == "create_entry"
    assert result["result"].unique_id == "GARDENA-123456"
    assert result["result"].title == "GARDENA-123456"


async def test_user_flow_falls_back_to_host_without_certificate_name(
    hass: HomeAssistant, mock_setup_entry
) -> None:
    """Without a named certificate the host stays the unique_id."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    with patch(PATCH_TRY_CONNECT, return_value=None):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_HOST: MOCK_HOST, CONF_PORT: MOCK_PORT, CONF_PASSWORD: MOCK_PASSWORD},
        )

    assert result["type"] == "create_entry"
    assert result["result"].unique_id == MOCK_HOST


async def test_user_flow_matches_discovered_entry_by_certificate_id(
    hass: HomeAssistant, mock_extract_hostname_from_cert
) -> None:
    """A manual entry for an already discovered gateway aborts as duplicate."""
    mock_extract_hostname_from_cert.return_value = "GARDENA-123456"
    MockConfigEntry(
        domain=DOMAIN,
        unique_id="GARDENA-123456",
        data={
            CONF_HOST: "192.168.1.5",
            CONF_PORT: MOCK_PORT,
            CONF_PASSWORD: MOCK_PASSWORD,
        },
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


async def test_user_flow_invalid_host(hass: HomeAssistant) -> None:
    """A malformed host is reported as invalid, not as an unknown error."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_HOST: "10.0.1.194 junk",
            CONF_PORT: MOCK_PORT,
            CONF_PASSWORD: MOCK_PASSWORD,
        },
    )

    assert result["type"] == "form"
    assert result["errors"] == {"base": "invalid_host"}


async def test_user_flow_rejects_out_of_range_port(hass: HomeAssistant) -> None:
    """A port outside 1-65535 fails schema validation, not a connection attempt."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )

    with pytest.raises(InvalidData):
        await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_HOST: MOCK_HOST, CONF_PORT: 70000, CONF_PASSWORD: MOCK_PASSWORD},
        )


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
        unique_id="GARDENA-123456",
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


async def test_reconfigure_migrates_unique_id_from_certificate(
    hass: HomeAssistant, mock_setup_entry, mock_extract_hostname_from_cert
) -> None:
    """Reconfiguring a host-based entry adopts the certificate gateway id."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=MOCK_HOST,
        data={CONF_HOST: MOCK_HOST, CONF_PORT: MOCK_PORT, CONF_PASSWORD: MOCK_PASSWORD},
    )
    entry.add_to_hass(hass)
    mock_extract_hostname_from_cert.return_value = "GARDENA-123456"

    result = await entry.start_reconfigure_flow(hass)
    with patch(PATCH_TRY_CONNECT, return_value=None):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_HOST: MOCK_HOST, CONF_PORT: MOCK_PORT, CONF_PASSWORD: MOCK_PASSWORD},
        )

    assert result["type"] == "abort"
    assert result["reason"] == "reconfigure_successful"
    assert entry.unique_id == "GARDENA-123456"


def _reconfigure_entry(hass: HomeAssistant) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=MOCK_HOST,
        data={CONF_HOST: MOCK_HOST, CONF_PORT: MOCK_PORT, CONF_PASSWORD: MOCK_PASSWORD},
    )
    entry.add_to_hass(hass)
    return entry


def _cloud_connection_default(result: ConfigFlowResult) -> bool | None:
    for key in result["data_schema"].schema:
        if key == CONF_CLOUD_CONNECTION:
            return key.default()
    return None


@pytest.mark.parametrize("connected", [True, False])
async def test_reconfigure_offers_the_cloud_connection_of_the_gateway(
    hass: HomeAssistant, mock_get_cloud_connection: AsyncMock, connected: bool
) -> None:
    """The form starts with the state the gateway has, not with a guess."""
    mock_get_cloud_connection.return_value = connected
    entry = _reconfigure_entry(hass)

    result = await entry.start_reconfigure_flow(hass)

    assert _cloud_connection_default(result) is connected
    mock_get_cloud_connection.assert_awaited_once_with()


async def test_reconfigure_hides_the_cloud_connection_if_it_cannot_be_read(
    hass: HomeAssistant, mock_get_cloud_connection: AsyncMock
) -> None:
    """A default that is not known would change the setting on save."""
    mock_get_cloud_connection.side_effect = ConfigApiError
    entry = _reconfigure_entry(hass)

    result = await entry.start_reconfigure_flow(hass)

    assert result["type"] == "form"
    assert CONF_CLOUD_CONNECTION not in [key for key in result["data_schema"].schema]


async def test_reconfigure_changes_the_cloud_connection(
    hass: HomeAssistant, mock_setup_entry, mock_set_cloud_connection: AsyncMock
) -> None:
    """The new state goes to the gateway and into the entry."""
    entry = _reconfigure_entry(hass)

    result = await entry.start_reconfigure_flow(hass)
    with patch(PATCH_TRY_CONNECT, return_value=None):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_HOST: MOCK_HOST,
                CONF_PORT: MOCK_PORT,
                CONF_PASSWORD: MOCK_PASSWORD,
                CONF_CLOUD_CONNECTION: False,
            },
        )

    assert result["type"] == "abort"
    assert result["reason"] == "reconfigure_successful"
    assert entry.data[CONF_CLOUD_CONNECTION] is False
    mock_set_cloud_connection.assert_awaited_once_with(False)


async def test_reconfigure_without_the_cloud_connection_leaves_it_alone(
    hass: HomeAssistant,
    mock_setup_entry,
    mock_get_cloud_connection: AsyncMock,
    mock_set_cloud_connection: AsyncMock,
) -> None:
    """A gateway whose setting could not be read keeps it as it is."""
    mock_get_cloud_connection.side_effect = ConfigApiError
    entry = _reconfigure_entry(hass)

    result = await entry.start_reconfigure_flow(hass)
    with patch(PATCH_TRY_CONNECT, return_value=None):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_HOST: MOCK_HOST, CONF_PORT: MOCK_PORT, CONF_PASSWORD: MOCK_PASSWORD},
        )

    assert result["reason"] == "reconfigure_successful"
    assert CONF_CLOUD_CONNECTION not in entry.data
    mock_set_cloud_connection.assert_not_awaited()


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (AuthenticationError, "invalid_auth"),
        (ConfigApiError, "cloud_connection_failed"),
    ],
)
async def test_reconfigure_cloud_connection_failure_keeps_the_form_open(
    hass: HomeAssistant,
    mock_set_cloud_connection: AsyncMock,
    error: type[Exception],
    expected: str,
) -> None:
    """Nothing is saved if the gateway does not take the new state."""
    mock_set_cloud_connection.side_effect = error
    entry = _reconfigure_entry(hass)

    result = await entry.start_reconfigure_flow(hass)
    with patch(PATCH_TRY_CONNECT, return_value=None):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_HOST: "192.168.1.200",
                CONF_PORT: MOCK_PORT,
                CONF_PASSWORD: MOCK_PASSWORD,
                CONF_CLOUD_CONNECTION: False,
            },
        )

    assert result["type"] == "form"
    assert result["errors"] == {"base": expected}
    assert entry.data[CONF_HOST] == MOCK_HOST
    assert CONF_CLOUD_CONNECTION not in entry.data


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


async def test_reconfigure_rejects_other_entry_host(
    hass: HomeAssistant, mock_setup_entry
) -> None:
    """Reconfiguring onto another entry's host aborts."""
    other_host = "192.168.1.200"
    MockConfigEntry(
        domain=DOMAIN,
        unique_id=other_host,
        data={
            CONF_HOST: other_host,
            CONF_PORT: MOCK_PORT,
            CONF_PASSWORD: MOCK_PASSWORD,
        },
    ).add_to_hass(hass)

    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=MOCK_HOST,
        data={CONF_HOST: MOCK_HOST, CONF_PORT: MOCK_PORT, CONF_PASSWORD: MOCK_PASSWORD},
    )
    entry.add_to_hass(hass)

    result = await entry.start_reconfigure_flow(hass)
    with patch(PATCH_TRY_CONNECT, return_value=None):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_HOST: other_host, CONF_PORT: MOCK_PORT, CONF_PASSWORD: MOCK_PASSWORD},
        )

    assert result["type"] == "abort"
    assert result["reason"] == "already_configured"


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


def _reauth_entry() -> MockConfigEntry:
    return MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_HOST: MOCK_HOST,
            CONF_PORT: MOCK_PORT,
            CONF_PASSWORD: MOCK_PASSWORD,
        },
    )


@pytest.mark.usefixtures("mock_setup_entry")
async def test_reauth_success(hass: HomeAssistant) -> None:
    """Reauthentication stores the new password and keeps the rest."""
    entry = _reauth_entry()
    entry.add_to_hass(hass)

    result = await entry.start_reauth_flow(hass)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reauth_confirm"

    with patch(PATCH_TRY_CONNECT, return_value=None) as try_connect:
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_PASSWORD: "new-password"}
        )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert entry.data[CONF_PASSWORD] == "new-password"
    assert entry.data[CONF_HOST] == MOCK_HOST
    assert try_connect.call_args.args[1:] == (MOCK_HOST, MOCK_PORT, "new-password")


@pytest.mark.parametrize("error", ["invalid_auth", "cannot_connect", "unknown"])
@pytest.mark.usefixtures("mock_setup_entry")
async def test_reauth_errors_can_be_recovered(hass: HomeAssistant, error: str) -> None:
    """A failed attempt shows the error and the flow still finishes."""
    entry = _reauth_entry()
    entry.add_to_hass(hass)
    result = await entry.start_reauth_flow(hass)

    with patch(PATCH_TRY_CONNECT, return_value=error):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_PASSWORD: "wrong"}
        )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": error}
    assert entry.data[CONF_PASSWORD] == MOCK_PASSWORD

    with patch(PATCH_TRY_CONNECT, return_value=None):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_PASSWORD: "right"}
        )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert entry.data[CONF_PASSWORD] == "right"
