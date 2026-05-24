"""Switches pour FastIron : activation de port et activation du PoE."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import FastIronCoordinator
from .entity import FastIronPortEntity, sanitize_port_id

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: FastIronCoordinator = hass.data[DOMAIN][entry.entry_id]
    entities: list[SwitchEntity] = []
    for port_id, port in coordinator.data.items():
        entities.append(FastIronPortAdminSwitch(coordinator, entry, port_id))
        if port.poe_capable:
            entities.append(FastIronPoESwitch(coordinator, entry, port_id))
    async_add_entities(entities)


class FastIronPortAdminSwitch(FastIronPortEntity, SwitchEntity):
    """Active ou désactive l'état admin d'un port (shutdown / no shutdown)."""

    _attr_icon = "mdi:ethernet"

    def __init__(self, coordinator, entry, port_id: str) -> None:
        super().__init__(coordinator, entry, port_id)
        self._attr_unique_id = f"{entry.entry_id}_{sanitize_port_id(port_id)}_admin"

    @property
    def name(self) -> str:
        return f"Port {self._port_label()}"

    @property
    def is_on(self) -> bool | None:
        return self._port.admin_state if self._port else None

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self.coordinator.api.set_port_admin_state(self._port_id, True)
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.coordinator.api.set_port_admin_state(self._port_id, False)
        await self.coordinator.async_request_refresh()


class FastIronPoESwitch(FastIronPortEntity, SwitchEntity):
    """Active ou désactive l'alimentation PoE d'un port."""

    _attr_icon = "mdi:power-plug"

    def __init__(self, coordinator, entry, port_id: str) -> None:
        super().__init__(coordinator, entry, port_id)
        self._attr_unique_id = f"{entry.entry_id}_{sanitize_port_id(port_id)}_poe"

    @property
    def name(self) -> str:
        return f"Port {self._port_label()}"

    @property
    def is_on(self) -> bool | None:
        return self._port.poe_enabled if self._port else None

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self.coordinator.api.set_port_poe(self._port_id, True)
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.coordinator.api.set_port_poe(self._port_id, False)
        await self.coordinator.async_request_refresh()
