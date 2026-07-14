<!--
SPDX-FileCopyrightText: 2026 GARDENA GmbH

SPDX-License-Identifier: Apache-2.0
-->

# Home Assistant Integration for GARDENA smart local API (preview)

[![hacs_badge](https://img.shields.io/badge/HACS-Default-orange.svg)](https://github.com/custom-components/hacs)

Home Assistant integration for GARDENA smart devices using local communication (not going through the cloud).

## Features

- Local communication with GARDENA smart devices
- Real-time updates via WebSocket

## Enabling WebSocket Support on the Gateway

The still experimental WebSocket service running on the gateway is disabled by default.
You can enable it through the gateway's web interface by visiting e.g.: https://GARDENA-123456.local

> [!TIP]
> You can also use the IP address found under "Garden Profile" in the GARDENA smart system app.

> [!NOTE]
> The password is the first block of the gateway ID printed on the back of the device, e.g.:
>
> ID: `1234abcd-996c-48f7-83dc-d2d1bac08e7e` → password: `1234abcd`

The advanced options are hidden behind a tiny grey arrow at the bottom of the page.

Alternatively, you can enable WebSocket support using e.g. `curl`:
```txt
gateway=GARDENA-123456.local
password=1234abcd

session=$(curl -H 'Content-Type: application/json' -d '{"password": "'"$password"'"}' --insecure https://$gateway/login | jq -r .session)

curl -X PUT -H "X-session: $session" -H 'Content-Type: application/json' -d '{"enable": true}' --insecure https://$gateway/websocket_api
```

The service `websocketd` is now listening on port 8443/TCP.

To disable WebSocket Support, you can run:
```txt
curl -X PUT -H "X-session: $session" -H 'Content-Type: application/json' -d '{"enable": false}' --insecure https://$gateway/websocket_api
```

## Installation

### HACS (Recommended)

1. [Install HACS] on your Home Assistant instance
2. Click on HACS in the sidebar
3. Search for "GARDENA smart local (preview)" and install the integration
4. Restart Home Assistant

[Install HACS]: https://hacs.xyz/docs/use/download/download/

### Manual Installation

1. Copy the `custom_components/gardena_smart_local_preview` directory to your Home Assistant's `custom_components` directory
2. Restart Home Assistant

## Configuration

After installation, go to **Settings → Devices & Services → Add Integration** and search for "GARDENA smart local". Enter the IP address or hostname of your gateway and the password.

The gateway can also be discovered automatically via Zeroconf — look for a notification in Home Assistant after installation.

### YAML configuration (legacy)

Manual YAML configuration is still supported:

```yaml
gardena_smart_local_preview:
  host: 192.168.1.100  # IP address or hostname of your GARDENA smart Gateway
  password: 0824b95b   # First eight characters of the gateway's ID
```

After adding the configuration, restart Home Assistant.

## Removal

1. Go to **Settings → Devices & Services**
2. Find the "GARDENA smart local (preview)" integration and click on it to see its entries (gateways)
3. On the gateway integration entry, click the three-dot menu and select **Delete**

If installed via HACS, you can also remove the integration files there: open HACS, find "GARDENA smart local (preview)", click on the three dots on the right and then on **Remove**. For a manual installation, delete the `custom_components/gardena_smart_local_preview` directory instead.

## Supported Devices

| Device                                     | Article no.                                | Entities                                                    |
| ------------------------------------------ | ------------------------------------------ | ----------------------------------------------------------- |
| GARDENA smart Water Control                | 19031-20                                   | Valve, temperature, battery, RF link quality                |
| GARDENA smart Water Control                | 19033-20                                   | Valve, temperature, battery                                 |
| GARDENA smart Dual Water Control           | 19034-20                                   | Valve, temperature, battery                                 |
| GARDENA smart Pipeline Water Control       | 19050-20                                   | Valve, temperature, battery                                 |
| GARDENA smart Irrigation Control           | 19032-20                                   | Valve, RF link quality                                      |
| GARDENA smart Irrigation Control           | 19035-20                                   | Valve                                                       |
| GARDENA smart Automatic Home & Garden Pump | 19080-20                                   | Switch, outlet pressure, outlet temperature, flow rate, total flow, flow since reset, pump state, operating mode, turn-on pressure, dripping alert timeout, reset flow / valve errors / temperature min-max |
| GARDENA smart Sensor                       | 19030-20                                   | Temperature, soil moisture, light, battery, RF link quality |
| GARDENA smart Sensor II                    | 19040-20                                   | Temperature, soil moisture, battery, RF link quality        |
| GARDENA smart Power Adapter                | 19095-20                                   | Switch                                                      |
| GARDENA smart SILENO                       | 19060-20, 19060-60                         | Lawn mower                                                  |
| GARDENA smart SILENO+                      | 19061-20, 19061-60, 19064-60, 19065-60     | Lawn mower                                                  |
| GARDENA smart SILENO city                  | 19066-20, 19069-20                         | Lawn mower                                                  |
| GARDENA smart SILENO life                  | 19113-20, 19114-20, 19115-20               | Lawn mower                                                  |
| GARDENA smart SILENO city (with LONA)      | 19602-66, 19603-60, 19605-60               | Lawn mower                                                  |
| GARDENA smart SILENO life (with LONA)      | 19701-60, 19702-60, 19703-66, 19704-60     | Lawn mower                                                  |
| GARDENA smart SILENO pro                   | 19802-20, 19802-22                         | Lawn mower                                                  |
| GARDENA smart SILENO max                   | 19901-22                                   | Lawn mower                                                  |
| GARDENA smart SILENO free                  | 19921-22, 19922-22, 19923-22               | Lawn mower                                                  |
| Flymo UltraLife                            | 970620501, 970620701, 970715101, 970715201 | Lawn mower                                                  |

> [!NOTE]
> The temperature sensor integrated into Water Control devices is intended solely for frost detection, not for precise real-time temperature tracking.

See [gardena-smart-local-api] for more details about the device types.

[gardena-smart-local-api]: https://github.com/cloudless-garden/gardena-smart-local-api
## Not Supported Devices

| Device                                | Article no.                                | Notes                                                       |
| ------------------------------------- | ------------------------------------------ | ----------------------------------------------------------- |
| GARDENA smart SILENO sense            | 19941-20, 19942-20                         | Can not be supported (not using the GARDENA smart gateway)  |

## Related Projects

This integration is built around the [gardena-smart-local-api] library.

## Contributing

### Debugging

#### Debugging on the Gateway

For hints on debugging on the gateway, please have a look at the README file in [gardena-smart-local-api].

### Licensing Compliance

```txt
uv run reuse lint
```
