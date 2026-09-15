# SPDX-FileCopyrightText: 2026 GARDENA GmbH
#
# SPDX-License-Identifier: Apache-2.0

"""Tests for the shared per-device entity setup used by all platforms."""

from __future__ import annotations

from functools import partial
from unittest.mock import MagicMock

import pytest

from custom_components.gardena_smart_local_preview.entity import (
    EntityFactories,
    async_setup_device_entities,
)


class _FakeEntity:
    def __init__(self, device_id: str, name: str) -> None:
        self.device_id = device_id
        self.name = name


def _device(device_id: str, valve_ids: tuple[int, ...] = ()) -> MagicMock:
    device = MagicMock()
    device.id = device_id
    device.valve_ids = list(valve_ids)
    return device


def _entities_for_device(device: MagicMock) -> EntityFactories:
    entities: EntityFactories = {"main": partial(_FakeEntity, device.id, "main")}
    for valve_id in device.valve_ids:
        name = f"valve_{valve_id}"
        entities[name] = partial(_FakeEntity, device.id, name)
    return entities


@pytest.fixture
def coordinator() -> MagicMock:
    coord = MagicMock()
    coord.data = {}
    coord.listeners = []
    coord.async_add_listener.side_effect = lambda cb: coord.listeners.append(cb)
    return coord


@pytest.fixture
def entry() -> MagicMock:
    subentry = MagicMock()
    subentry.data = {"device_id": "dev-1"}
    cfg = MagicMock()
    cfg.subentries = {"sub-1": subentry}
    return cfg


def _setup(entry, coordinator) -> MagicMock:
    async_add_entities = MagicMock()
    async_setup_device_entities(
        entry, coordinator, async_add_entities, _entities_for_device
    )
    return async_add_entities


def _added(async_add_entities: MagicMock) -> list[tuple[str, str, str | None]]:
    added = []
    for call in async_add_entities.call_args_list:
        for entity in call.args[0]:
            added.append(
                (entity.device_id, entity.name, call.kwargs["config_subentry_id"])
            )
    return added


def test_adds_entities_once_per_device_grouped_by_subentry(entry, coordinator):
    coordinator.data = {"dev-1": _device("dev-1", (0,)), "dev-2": _device("dev-2")}
    async_add_entities = _setup(entry, coordinator)

    assert sorted(_added(async_add_entities)) == [
        ("dev-1", "main", "sub-1"),
        ("dev-1", "valve_0", "sub-1"),
        ("dev-2", "main", None),
    ]

    async_add_entities.reset_mock()
    coordinator.listeners[0]()
    assert _added(async_add_entities) == []
    entry.async_on_unload.assert_called_once()


def test_readds_entities_after_last_device_was_removed(entry, coordinator):
    device = _device("dev-1")
    coordinator.data = {"dev-1": device}
    async_add_entities = _setup(entry, coordinator)

    coordinator.data = {}
    coordinator.listeners[0]()
    coordinator.data = {"dev-1": device}
    async_add_entities.reset_mock()
    coordinator.listeners[0]()

    assert _added(async_add_entities) == [("dev-1", "main", "sub-1")]


def test_readds_only_the_valve_that_came_back(entry, coordinator):
    coordinator.data = {"dev-1": _device("dev-1", (0, 1))}
    async_add_entities = _setup(entry, coordinator)

    coordinator.data = {"dev-1": _device("dev-1", (0,))}
    coordinator.listeners[0]()
    coordinator.data = {"dev-1": _device("dev-1", (0, 1))}
    async_add_entities.reset_mock()
    coordinator.listeners[0]()

    assert _added(async_add_entities) == [("dev-1", "valve_1", "sub-1")]
