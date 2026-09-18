<!--
SPDX-FileCopyrightText: 2026 GARDENA GmbH

SPDX-License-Identifier: Apache-2.0
-->

# AGENTS.md

Guidance for coding agents working in this repository: a Home Assistant
custom integration (preview) for GARDENA devices over the gateway's local
WebSocket API. It uses the [gardena-smart-local-api] library.

[gardena-smart-local-api]: https://github.com/cloudless-garden/gardena-smart-local-api

## Setup

```sh
uv sync --group dev
```

## Checks (run all before opening or updating a PR)

```sh
uv run ruff check
uv run ruff format --check
uv run pytest tests/ -v
uv run reuse lint
```

CI (`.github/workflows/validate.yml`, `compliance.yml`) also runs `hassfest`
and a HACS validation action; there is no local equivalent for those two, so
keep changes to `manifest.json`, `custom_components/gardena_smart_local_preview/`
layout, and `hacs.json` conservative and HA-integration-conventional.

## License headers (REUSE / SPDX)

Every source file starts with:

```py
# SPDX-FileCopyrightText: 2026 GARDENA GmbH
#
# SPDX-License-Identifier: Apache-2.0
```

`uv run reuse lint` fails the build if a new file is missing this. Copy the
header from an existing file of the same type rather than retyping it.

## Layout

- `custom_components/gardena_smart_local_preview/` — the integration.
  One file per platform (`switch.py`, `valve.py`, `number.py`,
  `lawn_mower.py`, `sensor.py`, …), plus `coordinator.py` (the WebSocket
  connection and device state), `entity.py` (shared entity base class and
  per-device config-subentry helpers), `const.py`, `config_flow.py`.
- `custom_components/gardena_smart_local_preview/translations/` —
  `en.json`, `de.json`, `fr.json`. Keep all three in sync: a new config
  string, entity name, or service needs an entry in every file, not just
  `en.json`.
- `tests/` — pytest with `pytest-homeassistant-custom-component`.
  `asyncio_mode = "auto"` is set in `pyproject.toml`, so async test functions
  do not need `@pytest.mark.asyncio`.

## Conventions

- Entities extend `GardenaEntity` (in `entity.py`) and read state from
  `self.coordinator.data`, not from a cached snapshot — the coordinator owns
  device state.
- A device's user-configurable default (valve/pump/mower duration, etc.) is
  stored in the device's config subentry via the `get_*_duration_*` /
  `async_set_*_duration_*` helper pairs in `entity.py`, not in `ConfigEntry.data`
  directly — subentries stay settable while the gateway is unreachable. An
  entity that only reads/writes subentry data (not device state) overrides
  `available` to always return `True`.
- A platform that accepts a per-call override on top of a configured default
  (`open_valve`, `enable_output`, `start_pump`, `start_mowing`) registers a
  custom service via `entity_platform.async_register_entity_service` with an
  optional `duration` field, falling back to the configured default when the
  field is omitted. Follow this pattern for new timed actions instead of
  inventing a new shape — see `services.yaml` and the `async_*_for` methods
  in `switch.py`/`valve.py`/`lawn_mower.py`.
- Write "GARDENA" (all caps) in prose, comments, docstrings, and commit
  messages — except inside compound package/domain identifiers such as
  `gardena_smart_local_preview` or `gardena-smart-local-api`, which stay
  lowercase.
- Say "gateway", not "hub". Say "inclusion"/"exclusion", not "pairing", when
  talking about adding or removing a device.

## Git

- Feature branches: `gardena/<initials>/<short-slug>`.
- One logical change per commit; do not mix unrelated fixes into a feature
  commit.
- Commit body explains *why*, not a walkthrough of the diff.
- New PRs: open as draft, one focused change, no "Test Plan" section.
