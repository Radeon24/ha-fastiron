"""DataUpdateCoordinator pour FastIron."""
from __future__ import annotations

import logging
import time
from datetime import timedelta

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import FastIronAPI, FastIronError, FastIronPlatformStatus, FastIronPort
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


class FastIronCoordinator(DataUpdateCoordinator[dict[str, FastIronPort]]):
    """Coordonnateur de données pour un switch FastIron.

    Toutes les entités partagent ce coordinateur et sont mises à jour
    lors de chaque poll vers le switch.
    """

    def __init__(
        self,
        hass: HomeAssistant,
        api: FastIronAPI,
        scan_interval: int,
        sw_model: str = "FastIron",
        sw_firmware: str = "",
    ) -> None:
        self.api = api
        self.sw_model = sw_model
        self.sw_firmware = sw_firmware
        self.temperature: float | None = None
        self.platform: FastIronPlatformStatus | None = None
        self._prev_ports: dict[str, FastIronPort] | None = None
        self._prev_time: float | None = None
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=scan_interval),
        )

    async def _async_update_data(self) -> dict[str, FastIronPort]:
        """Récupère ports, débits et état de santé depuis l'API."""
        try:
            ports = await self.api.get_ports()
            self.platform = await self.api.get_platform_status()
        except FastIronError as err:
            raise UpdateFailed(f"Erreur FastIron : {err}") from err

        self.temperature = self.platform.temperature if self.platform else None

        ports_dict = {port.id: port for port in ports}

        # Calcul du débit (delta octets / temps écoulé)
        now = time.monotonic()
        if self._prev_ports is not None and self._prev_time is not None:
            elapsed = now - self._prev_time
            if elapsed > 0:
                for port_id, port in ports_dict.items():
                    prev = self._prev_ports.get(port_id)
                    if prev is not None:
                        rx_delta = port.rx_octets - prev.rx_octets
                        tx_delta = port.tx_octets - prev.tx_octets
                        if rx_delta >= 0:
                            port.rx_rate_mbps = round(
                                (rx_delta * 8) / (elapsed * 1_000_000), 3
                            )
                        if tx_delta >= 0:
                            port.tx_rate_mbps = round(
                                (tx_delta * 8) / (elapsed * 1_000_000), 3
                            )
        self._prev_ports = ports_dict
        self._prev_time = now

        return ports_dict
