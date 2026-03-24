# Home Assistant Integration for GARDENA smart local API (preview)

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/custom-components/hacs)

Home Assistant integration for GARDENA smart devices using local communication (not going through the cloud).

## Features

- Local communication with GARDENA smart devices
- Real-time updates via WebSocket

## Enabling WebSocket Support on the Gateway

The still experimental WebSocket service running on the gateway is disabled by default.
At least for now, you need shell access to your GARDENA smart Gateway to enable it.
The instructions for that can be found in the [smart-garden-gateway-public] repository.

On the gateway, run the following commands:

```txt
touch /etc/enable-websocketd
systemctl restart firewall
systemctl start websocketd
```

[smart-garden-gateway-public]: https://github.com/husqvarnagroup/smart-garden-gateway-public#getting-access

## Installation

### HACS (Recommended)

1. Open HACS in your Home Assistant instance
2. Click on "Integrations"
3. Click the three dots in the top right corner
4. Select "Custom repositories"
5. Add the repository URL: `https://github.com/cloudless-garden/ha-gardena-smart-local-preview`
6. Select category: "Integration"
7. Click "Add"
8. Find "GARDENA smart local (preview)" in the integration list and install it
9. Restart Home Assistant

### Manual Installation

1. Copy the `custom_components/gardena_smart_local_preview` directory to your Home Assistant's `custom_components` directory
2. Restart Home Assistant

## Configuration

Add the following to your `configuration.yaml`:

```yaml
gardena_smart_local_preview:
  host: 192.168.1.100  # IP address or hostname of your GARDENA smart Gateway
  password: 0824b95b   # First eight characters of the gateway's ID
```

> [!TIP]
> The password is the first block of the gateway ID printed on the back of the device.
> (example: `0824b95b-996c-48f7-83dc-d2d1bac08e7e` → password: `0824b95b`)

After adding the configuration, restart Home Assistant.

## Supported Devices

- GARDENA smart Water Control (Article no. 19031-20)
- more to come...

## Related Projects

This integration is built around the [gardena-smart-local-api](https://github.com/cloudless-garden/gardena-smart-local-api) library.
