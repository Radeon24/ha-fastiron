"""Binary sensors pour FastIron : liaison des ports, PSU et ventilateurs."""
from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import FastIronCoordinator
from .entity import FastIronPortEntity, build_device_info, sanitize_port_id


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: FastIronCoordinator = hass.data[DOMAIN][entry.entry_id]
    entities: list[BinarySensorEntity] = [
        FastIronLinkSensor(coordinator, entry, port_id)
        for port_id in coordinator.data
    ]
    if coordinator.platform is not None:
        for idx, _, _ in coordinator.platform.psu:
            entities.append(FastIronPsuSensor(coordinator, entry, idx))
        for idx, _, _ in coordinator.platform.fans:
            entities.append(FastIronFanSensor(coordinator, entry, idx))
    async_add_entities(entities)


class FastIronLinkSensor(FastIronPortEntity, BinarySensorEntity):
    """Indique si la liaison physique du port est active (up)."""

    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY

    def __init__(self, coordinator, entry, port_id: str) -> None:
        super().__init__(coordinator, entry, port_id)
        self._attr_unique_id = f"{entry.entry_id}_{sanitize_port_id(port_id)}_link"

    @property
    def name(self) -> str:
        return f"Port {self._port_label()} liaison"

    @property
    def is_on(self) -> bool | None:
        return self._port.link_state if self._port else None

    @property
    def extra_state_attributes(self) -> dict:
        port = self._port
        if not port:
            return {}
        return {
            "port_id": port.id,
            "port_short": port.short_name,
            "description": port.description,
            "speed_mbps": port.speed_mbps,
            "admin_state": port.admin_state,
        }


class FastIronPsuSensor(CoordinatorEntity[FastIronCoordinator], BinarySensorEntity):
    """Défaut d'alimentation (on = problème détecté)."""

    _attr_device_class = BinarySensorDeviceClass.PROBLEM
    _attr_has_entity_name = True

    def __init__(
        self, coordinator: FastIronCoordinator, entry: ConfigEntry, index: int
    ) -> None:
        super().__init__(coordinator)
        self._index = index
        self._attr_unique_id = f"{entry.entry_id}_psu_{index}"
        self._attr_name = f"Alimentation {index}"
        self._attr_device_info = build_device_info(entry, coordinator)

    def _psu_entry(self) -> tuple[int, str, bool] | None:
        if self.coordinator.platform is None:
            return None
        return next(
            (t for t in self.coordinator.platform.psu if t[0] == self._index), None
        )

    @property
    def is_on(self) -> bool | None:
        entry = self._psu_entry()
        return None if entry is None else not entry[2]

    @property
    def extra_state_attributes(self) -> dict:
        entry = self._psu_entry()
        return {"status": entry[1]} if entry else {}


class FastIronFanSensor(CoordinatorEntity[FastIronCoordinator], BinarySensorEntity):
    """Défaut ventilateur (on = problème détecté)."""

    _attr_device_class = BinarySensorDeviceClass.PROBLEM
    _attr_has_entity_name = True

    def __init__(
        self, coordinator: FastIronCoordinator, entry: ConfigEntry, index: int
    ) -> None:
        super().__init__(coordinator)
        self._index = index
        self._attr_unique_id = f"{entry.entry_id}_fan_{index}"
        self._attr_name = f"Ventilateur {index}"
        self._attr_device_info = build_device_info(entry, coordinator)

    def _fan_entry(self) -> tuple[int, str, bool] | None:
        if self.coordinator.platform is None:
            return None
        return next(
            (t for t in self.coordinator.platform.fans if t[0] == self._index), None
        )

    @property
    def is_on(self) -> bool | None:
        entry = self._fan_entry()
        return None if entry is None else not entry[2]

    @property
    def extra_state_attributes(self) -> dict:
        entry = self._fan_entry()
        return {"status": entry[1]} if entry else {}
