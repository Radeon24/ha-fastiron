"""Sensors pour FastIron : vitesse, trafic, erreurs, PoE et température."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfDataRate, UnitOfInformation, UnitOfPower, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import FastIronPort
from .const import CONF_ENABLE_DIAGNOSTIC_SENSORS, DEFAULT_ENABLE_DIAGNOSTIC_SENSORS, DOMAIN
from .coordinator import FastIronCoordinator
from .entity import FastIronPortEntity, build_device_info, sanitize_port_id


@dataclass(frozen=True)
class _PortSensorDesc(SensorEntityDescription):
    label: str = ""
    value_fn: Callable[[FastIronPort], float | int | None] = field(
        default=lambda p: None
    )
    poe_only: bool = False
    diagnostic: bool = False


_PORT_SENSORS: list[_PortSensorDesc] = [
    _PortSensorDesc(
        key="speed",
        label="vitesse",
        native_unit_of_measurement="Mbit/s",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:speedometer",
        value_fn=lambda p: p.speed_mbps,
    ),
    _PortSensorDesc(
        key="rx",
        label="octets reçus",
        device_class=SensorDeviceClass.DATA_SIZE,
        native_unit_of_measurement=UnitOfInformation.BYTES,
        state_class=SensorStateClass.TOTAL_INCREASING,
        icon="mdi:arrow-down-bold",
        value_fn=lambda p: p.rx_octets,
    ),
    _PortSensorDesc(
        key="tx",
        label="octets envoyés",
        device_class=SensorDeviceClass.DATA_SIZE,
        native_unit_of_measurement=UnitOfInformation.BYTES,
        state_class=SensorStateClass.TOTAL_INCREASING,
        icon="mdi:arrow-up-bold",
        value_fn=lambda p: p.tx_octets,
    ),
    _PortSensorDesc(
        key="rx_rate",
        label="débit RX",
        device_class=SensorDeviceClass.DATA_RATE,
        native_unit_of_measurement=UnitOfDataRate.MEGABITS_PER_SECOND,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:download-network",
        value_fn=lambda p: p.rx_rate_mbps,
    ),
    _PortSensorDesc(
        key="tx_rate",
        label="débit TX",
        device_class=SensorDeviceClass.DATA_RATE,
        native_unit_of_measurement=UnitOfDataRate.MEGABITS_PER_SECOND,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:upload-network",
        value_fn=lambda p: p.tx_rate_mbps,
    ),
    _PortSensorDesc(
        key="rx_packets",
        label="paquets reçus",
        state_class=SensorStateClass.TOTAL_INCREASING,
        icon="mdi:arrow-down",
        value_fn=lambda p: p.rx_packets,
        diagnostic=True,
    ),
    _PortSensorDesc(
        key="tx_packets",
        label="paquets envoyés",
        state_class=SensorStateClass.TOTAL_INCREASING,
        icon="mdi:arrow-up",
        value_fn=lambda p: p.tx_packets,
        diagnostic=True,
    ),
    _PortSensorDesc(
        key="rx_errors",
        label="erreurs RX",
        state_class=SensorStateClass.TOTAL_INCREASING,
        icon="mdi:alert-circle-outline",
        value_fn=lambda p: p.rx_errors,
        diagnostic=True,
    ),
    _PortSensorDesc(
        key="tx_errors",
        label="erreurs TX",
        state_class=SensorStateClass.TOTAL_INCREASING,
        icon="mdi:alert-circle",
        value_fn=lambda p: p.tx_errors,
        diagnostic=True,
    ),
    _PortSensorDesc(
        key="rx_discards",
        label="discards RX",
        state_class=SensorStateClass.TOTAL_INCREASING,
        icon="mdi:trash-can-outline",
        value_fn=lambda p: p.rx_discards,
        diagnostic=True,
    ),
    _PortSensorDesc(
        key="tx_discards",
        label="discards TX",
        state_class=SensorStateClass.TOTAL_INCREASING,
        icon="mdi:trash-can",
        value_fn=lambda p: p.tx_discards,
        diagnostic=True,
    ),
    _PortSensorDesc(
        key="rx_fcs",
        label="erreurs FCS",
        state_class=SensorStateClass.TOTAL_INCREASING,
        icon="mdi:close-network-outline",
        value_fn=lambda p: p.rx_fcs_errors,
        diagnostic=True,
    ),
    _PortSensorDesc(
        key="poe_power",
        label="consommation PoE",
        device_class=SensorDeviceClass.POWER,
        native_unit_of_measurement=UnitOfPower.WATT,
        state_class=SensorStateClass.MEASUREMENT,
        poe_only=True,
        value_fn=lambda p: p.poe_power_w,
    ),
    _PortSensorDesc(
        key="poe_allocated",
        label="PoE alloué",
        device_class=SensorDeviceClass.POWER,
        native_unit_of_measurement=UnitOfPower.WATT,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:flash-outline",
        poe_only=True,
        value_fn=lambda p: p.poe_power_allocated_w,
    ),
]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: FastIronCoordinator = hass.data[DOMAIN][entry.entry_id]
    enable_diag: bool = entry.options.get(
        CONF_ENABLE_DIAGNOSTIC_SENSORS, DEFAULT_ENABLE_DIAGNOSTIC_SENSORS
    )
    entities: list[SensorEntity] = [FastIronTemperatureSensor(coordinator, entry)]
    for port_id, port in coordinator.data.items():
        for desc in _PORT_SENSORS:
            if desc.poe_only and not port.poe_capable:
                continue
            if desc.diagnostic and not enable_diag:
                continue
            entities.append(FastIronPortSensor(coordinator, entry, port_id, desc))
    async_add_entities(entities)


class FastIronPortSensor(FastIronPortEntity, SensorEntity):
    """Capteur générique pour une métrique de port FastIron."""

    entity_description: _PortSensorDesc

    def __init__(
        self,
        coordinator: FastIronCoordinator,
        entry: ConfigEntry,
        port_id: str,
        desc: _PortSensorDesc,
    ) -> None:
        super().__init__(coordinator, entry, port_id)
        self.entity_description = desc
        safe = sanitize_port_id(port_id)
        self._attr_unique_id = f"{entry.entry_id}_{safe}_{desc.key}"

    @property
    def name(self) -> str:
        return f"Port {self._port_label()} {self.entity_description.label}"

    @property
    def native_value(self) -> float | int | None:
        port = self._port
        return self.entity_description.value_fn(port) if port else None


class FastIronTemperatureSensor(CoordinatorEntity[FastIronCoordinator], SensorEntity):
    """Température actuelle du switch en °C."""

    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_has_entity_name = True
    _attr_name = "Température"

    def __init__(self, coordinator: FastIronCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_temperature"
        self._attr_device_info = build_device_info(entry, coordinator)

    @property
    def native_value(self) -> float | None:
        return self.coordinator.temperature
