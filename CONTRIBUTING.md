<!--
SPDX-FileCopyrightText: 2026 GARDENA GmbH

SPDX-License-Identifier: Apache-2.0
-->

# Contributing

Thank you for helping with the GARDENA smart local integration for Home
Assistant. This guide explains how to report problems, how to set up a
development environment, and what we look for in a pull request.

The integration talks to the gateway through the
[gardena-smart-local-api] library. If your change is about the protocol
itself (messages, device models, how a value is decoded), it most likely
belongs in the library, not here.

[gardena-smart-local-api]: https://github.com/cloudless-garden/gardena-smart-local-api

## Reporting a problem

Open an [issue] and pick the template that fits. For a bug, please include:

- The versions of Home Assistant and of this integration.
- The device and its article number (see [Supported Devices] in the README).
- The diagnostics: open the gateway entry or the device under
  **Settings → Devices & Services**, open the three-dot menu and select
  **Download diagnostics**. The password is removed from the file.
- Debug logs of the problem, if you can reproduce it:

  ```yaml
  logger:
    logs:
      custom_components.gardena_smart_local_preview: debug
      gardena_smart_local_api: debug
  ```

For questions and ideas that are not a concrete feature request yet, use
[Discussions].

[issue]: https://github.com/cloudless-garden/ha-gardena-smart-local-preview/issues/new/choose
[Supported Devices]: README.md#supported-devices
[Discussions]: https://github.com/cloudless-garden/ha-gardena-smart-local-preview/discussions

## Development setup

The project uses [uv]. Install the development dependencies with:

```sh
uv sync --group dev
```

[uv]: https://docs.astral.sh/uv/

### Repository layout

- `custom_components/gardena_smart_local_preview/`: the integration. There
  is one file per platform (`switch.py`, `valve.py`, `number.py`,
  `lawn_mower.py`, `sensor.py`, and so on). `coordinator.py` holds the
  WebSocket connection and the device state. `entity.py` holds the shared
  entity base class and the helpers for per-device config subentries.
- `custom_components/gardena_smart_local_preview/translations/`: one file per
  language.
- `blueprints/`: the script blueprints described in the README.
- `tests/`: pytest tests that use
  `pytest-homeassistant-custom-component`. `asyncio_mode = "auto"` is set, so
  async tests do not need `@pytest.mark.asyncio`.

### Checks

Run these before you open or update a pull request. CI runs them too:

```sh
uv run ruff check
uv run ruff format --check
uv run pytest tests/ -v
uv run reuse lint
```

CI also runs `hassfest` and the HACS validation, which have no local
equivalent. Keep changes to `manifest.json`, `hacs.json` and the layout of
the integration directory close to the usual Home Assistant conventions. The
versions in `manifest.json` and `pyproject.toml` must match.

### Debugging on the gateway

For hints on debugging on the gateway itself, see the README of
[gardena-smart-local-api].

## Code conventions

- Entities extend `GardenaEntity` (in `entity.py`) and read their state from
  `self.coordinator.data`. The coordinator owns the device state, so do not
  keep a copy of it in the entity.
- A user-configurable default of a device, such as the valve, pump or mower
  duration, is stored in the config subentry of that device. Use the
  `get_*_duration_*` and `async_set_*_duration_*` helpers in `entity.py`.
  Subentries stay editable while the gateway is unreachable, so an entity that
  only reads and writes subentry data overrides `available` to always return
  `True`.
- Timed actions (`open_valve`, `enable_output`, `start_pump`, `start_mowing`)
  are entity services with an optional `duration` field. Without it, the
  configured default is used. Follow this pattern for a new timed action, see
  `services.yaml` and the `async_*_for` methods in `switch.py`, `valve.py` and
  `lawn_mower.py`.

### Wording

- Write "GARDENA" in capitals in prose, comments, docstrings and commit
  messages. Package and domain names such as `gardena_smart_local_preview`
  and `gardena-smart-local-api` stay lowercase.
- Say "gateway", not "hub".
- Say "inclusion" and "exclusion", not "pairing", for adding and removing a
  device.

## Translations

`en.json` is the source of every user-facing text (config flow, entity
names, services, repairs). Add a new string there first.

Never copy the English text into another language file. Home Assistant
already falls back to English for a missing key, and a copied English text
hides that the translation is missing.

A pull request does not have to translate every new string, because nobody
speaks all supported languages. If you can, add the other languages too. A
machine translation is a good start. List the keys of a machine translation in
`PENDING_REVIEW` in `tests/test_translations.py`, and remove them once a native
speaker has approved the text.

To add a new language:

1. Copy `en.json` to `<language code>.json` and translate the values. Keep the
   keys and the `{placeholders}` unchanged. Remove the keys you cannot
   translate yet, they fall back to English.
2. JSON files cannot hold a license header, so add an entry for your file to
   `REUSE.toml` with your name as the copyright holder. See the entries for
   `fr.json` and `pl.json`.
3. Run `uv run reuse lint`.

We are thankful for every new language. A translation makes the integration
easier to use for more people, and we see that as important.

We also want every translation to stay of high quality and up to date. For
this reason, please be open to joining the project as a collaborator when you
add a language. GitHub only allows a review request from a collaborator, so
this lets us add you as a reviewer on pull requests that change the texts in
your language. Being a reviewer is optional but highly appreciated. A language
without a reviewer is still welcome.

## License headers

Every file needs an SPDX license header, or `uv run reuse lint` fails. Copy
the header from an existing file of the same type, for example for Python:

```py
# SPDX-FileCopyrightText: 2026 GARDENA GmbH
#
# SPDX-License-Identifier: Apache-2.0
```

Files that cannot hold a comment, such as JSON and images, are listed in
`REUSE.toml` instead.

## Commits and pull requests

- Keep one logical change per commit. Do not mix an unrelated fix into a
  feature commit.
- Write a short subject line in the imperative mood, like the existing
  history ("Add a reauthentication flow"). Use the commit body to explain why the
  change is needed. The diff already shows what changed.
- Keep a pull request focused on one change. Open it as a draft while you are
  still working on it.
- Maintainers name their branches `gardena/<initials>/<short-slug>`. In a
  fork, any branch name is fine.
