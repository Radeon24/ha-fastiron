"""Classe de base partagée par toutes les entités FastIron."""
from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import FastIronPort
from .const import DOMAIN, ENTRY_SW_HOSTNAME
from .coordinator import FastIronCoordinator


def sanitize_port_id(port_id: str) -> str:
    """Transforme un port_id en chaîne sûre pour unique_id ('ethernet 1/1/1' → 'ethernet_1_1_1')."""
    return port_id.replace(" ", "_").replace("/", "_")


def build_device_info(entry: ConfigEntry, coordinator: FastIronCoordinator) -> DeviceInfo:
    """Construit le DeviceInfo à partir des données de configuration."""
    return DeviceInfo(
        identifiers={(DOMAIN, entry.entry_id)},
        name=entry.data.get(ENTRY_SW_HOSTNAME, entry.data[CONF_HOST]),
        manufacturer="Ruckus Networks",
        model=coordinator.sw_model,
        sw_version=coordinator.sw_firmware,
        configuration_url=f"https://{entry.data[CONF_HOST]}:{entry.data.get('port', 443)}",
    )


class FastIronPortEntity(CoordinatorEntity[FastIronCoordinator]):
    """Classe de base pour toutes les entités associées à un port."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: FastIronCoordinator,
        entry: ConfigEntry,
        port_id: str,
    ) -> None:
        super().__init__(coordinator)
        self._port_id = port_id
        self._attr_device_info = build_device_info(entry, coordinator)

    @property
    def _port(self) -> FastIronPort | None:
        return self.coordinator.data.get(self._port_id)

    def _port_label(self) -> str:
        """Retourne Et<numéro> ou Et<numéro>_<description> si définie (ex: Et1/1/1_Uplink)."""
        port = self._port
        if port:
            prefix = f"Et{port.short_name}"
            return f"{prefix}_{port.description}" if port.description else prefix
        return self._port_id
