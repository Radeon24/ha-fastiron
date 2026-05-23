"""Bouton de redémarrage pour FastIron."""
from __future__ import annotations

from homeassistant.components.button import ButtonDeviceClass, ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import FastIronCoordinator
from .entity import build_device_info


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: FastIronCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([FastIronRebootButton(coordinator, entry)])


class FastIronRebootButton(CoordinatorEntity[FastIronCoordinator], ButtonEntity):
    """Bouton pour redémarrer le switch FastIron."""

    _attr_device_class = ButtonDeviceClass.RESTART
    _attr_has_entity_name = True
    _attr_name = "Redémarrer"

    def __init__(self, coordinator: FastIronCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_reboot"
        self._attr_device_info = build_device_info(entry, coordinator)

    async def async_press(self) -> None:
        await self.coordinator.api.reboot()
