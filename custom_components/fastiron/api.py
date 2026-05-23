"""Client RESTCONF pour les switches Ruckus/Brocade ICX sous FastIron 9.

Protocole : RESTCONF (RFC 8040) — PAS une API REST propriétaire.
Auth      : HTTP Basic Auth, compte FastIron avec privilege 0 obligatoire.
Content   : application/yang-data+json

Endpoints utilisés (doc FastIron RESTCONF Programmers Guide 09.0.10) :
  GET  /restconf/data/system/config/hostname
  GET  /restconf/data/openconfig-platform:components  (modèle, température, PSU, ventilateurs)
  GET  /restconf/data/interfaces                       (tous les ports)
  PATCH /restconf/data/interfaces/interface=<id>/config
        {"config": {"enabled": true|false}}            (admin state)
  PATCH /restconf/data/interfaces/interface=<id>/ethernet/poe/config
        {"config": {"enabled": true|false}}            (PoE on/off)
  POST /restconf/operations/boot-sys-flash
        {"icx-openconfig-platform-aug:input": {"primary": [null]}}  (reboot)

<id> = nom du port URL-encodé intégralement (RFC 3986) :
  "ethernet 1/1/1" → "ethernet%201%2F1%2F1"

Unités retournées par l'API :
  - power-used / power-allocated : mW (string float), converti en W ici
  - in-octets / out-octets : octets 64 bits (string int)
  - actual_temperature : °C (int)
  - power-supply-N-status / fan-N-status : chaîne de texte libre
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import quote

import aiohttp

_LOGGER = logging.getLogger(__name__)

# openconfig-if-ethernet:SPEED_* → Mbps
_OC_SPEED_MAP = {
    "SPEED_10MB": 10,
    "SPEED_100MB": 100,
    "SPEED_1GB": 1000,
    "SPEED_2500MB": 2500,
    "SPEED_5GB": 5000,
    "SPEED_10GB": 10000,
    "SPEED_25GB": 25000,
    "SPEED_40GB": 40000,
    "SPEED_100GB": 100000,
}


def _parse_oc_speed(speed_str: str) -> int:
    for key, mbps in _OC_SPEED_MAP.items():
        if key in speed_str:
            return mbps
    return 0


def _mw_to_w(raw: Any) -> float:
    """Convertit une valeur mW (string ou number) en W, arrondie à 2 décimales."""
    try:
        return round(float(raw) / 1000, 2)
    except (TypeError, ValueError):
        return 0.0


def _get_interfaces(data: dict) -> list[dict]:
    """Extrait la liste des interfaces depuis la réponse RESTCONF.

    Supporte les deux namespaces selon la version du firmware :
      {"openconfig-interfaces:interfaces": {"interface": [...]}}
      {"interfaces": {"interface": [...]}}
    """
    for key in ("openconfig-interfaces:interfaces", "interfaces"):
        container = data.get(key)
        if isinstance(container, dict):
            ifaces = container.get("interface", [])
            if ifaces:
                return ifaces
    return data if isinstance(data, list) else []


_AUG = "icx-openconfig-platform-aug:"


@dataclass
class FastIronPlatformStatus:
    """Données de santé du switch : température, PSU, ventilateurs."""

    temperature: float | None = None
    # [(index, texte_brut, is_ok)]
    psu: list[tuple[int, str, bool]] = field(default_factory=list)
    fans: list[tuple[int, str, bool]] = field(default_factory=list)


class FastIronError(Exception):
    """Erreur générique FastIron."""


class FastIronAuthError(FastIronError):
    """Identifiants invalides ou accès refusé (privilege 0 requis)."""


class FastIronConnectionError(FastIronError):
    """Switch injoignable ou timeout."""


class FastIronPort:
    """Représente un port Ethernet physique avec l'ensemble de ses métriques."""

    def __init__(self, data: dict) -> None:
        self.id: str = data.get("name", "")

        cfg = data.get("config", {})
        state = data.get("state", {})
        eth = data.get("openconfig-if-ethernet:ethernet", {})
        eth_state = eth.get("state", {})
        counters = state.get("counters", {})

        self.description: str = cfg.get("description", state.get("description", ""))
        self.admin_state: bool = bool(cfg.get("enabled", True))
        self.link_state: bool = state.get("oper-status", "DOWN").upper() == "UP"

        speed_str = eth_state.get("negotiated-port-speed", "SPEED_UNKNOWN")
        self.speed_mbps: int = _parse_oc_speed(speed_str)

        # Compteurs trafic (string 64 bits dans l'API)
        self.rx_octets: int = int(counters.get("in-octets", 0))
        self.tx_octets: int = int(counters.get("out-octets", 0))
        self.rx_packets: int = int(counters.get("in-pkts", 0))
        self.tx_packets: int = int(counters.get("out-pkts", 0))
        self.rx_errors: int = int(counters.get("in-errors", 0))
        self.tx_errors: int = int(counters.get("out-errors", 0))
        self.rx_discards: int = int(counters.get("in-discards", 0))
        self.tx_discards: int = int(counters.get("out-discards", 0))
        self.rx_fcs_errors: int = int(counters.get("in-fcs-errors", 0))

        # PoE
        poe = (
            eth.get("icx-openconfig-if-poe-aug:poe")
            or eth.get("openconfig-if-poe:poe")
            or eth.get("poe")
        )
        if poe is not None:
            self.poe_capable = True
            poe_cfg = poe.get("config", {})
            poe_state = poe.get("state", {})
            self.poe_enabled: bool = bool(poe_cfg.get("enabled", False))
            self.poe_power_w: float = _mw_to_w(poe_state.get("power-used", 0))
            self.poe_power_allocated_w: float = _mw_to_w(
                poe_state.get("power-allocated", 0)
            )
        else:
            self.poe_capable = False
            self.poe_enabled = False
            self.poe_power_w = 0.0
            self.poe_power_allocated_w = 0.0

        # Calculé par le coordinator à partir des deltas inter-polls
        self.rx_rate_mbps: float | None = None
        self.tx_rate_mbps: float | None = None

    @property
    def short_name(self) -> str:
        """Retourne le numéro court du port (ex: "1/1/1" depuis "ethernet 1/1/1")."""
        parts = self.id.split(None, 1)
        return parts[1] if len(parts) > 1 else self.id

    def __repr__(self) -> str:
        return f"<FastIronPort {self.id!r} link={'up' if self.link_state else 'down'}>"


class FastIronAPI:
    """Client RESTCONF asynchrone pour FastIron 9."""

    _TIMEOUT = aiohttp.ClientTimeout(total=10)
    _YANG_JSON = "application/yang-data+json"

    def __init__(
        self,
        host: str,
        port: int,
        username: str,
        password: str,
        verify_ssl: bool = False,
    ) -> None:
        self._base_url = f"https://{host}:{port}/restconf"
        self._auth = aiohttp.BasicAuth(username, password)
        self._ssl: bool | None = None if verify_ssl else False
        self._session: aiohttp.ClientSession | None = None

    def _ensure_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            connector = aiohttp.TCPConnector(ssl=self._ssl)
            self._session = aiohttp.ClientSession(
                auth=self._auth,
                connector=connector,
                headers={
                    "Accept": self._YANG_JSON,
                    "Content-Type": self._YANG_JSON,
                },
            )
        return self._session

    async def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        session = self._ensure_session()
        url = f"{self._base_url}{path}"
        try:
            async with session.request(
                method, url, timeout=self._TIMEOUT, **kwargs
            ) as resp:
                if resp.status == 401:
                    raise FastIronAuthError(
                        "Authentification refusée — vérifier que le compte a privilege 0"
                    )
                if resp.status == 403:
                    raise FastIronAuthError("Accès refusé (403)")
                resp.raise_for_status()
                if resp.status == 204 or resp.content_length == 0:
                    return None
                return await resp.json(content_type=None)
        except (aiohttp.ClientConnectorError, aiohttp.ServerTimeoutError) as err:
            raise FastIronConnectionError(str(err)) from err

    async def get_system_info(self) -> dict:
        """Retourne hostname et modèle du switch."""
        info: dict[str, str] = {}
        try:
            data = await self._request("GET", "/data/system/config/hostname")
            if data:
                info["hostname"] = data.get("openconfig-system:hostname", "")
        except FastIronError:
            pass
        try:
            data = await self._request(
                "GET", "/data/openconfig-platform:components"
            )
            if data:
                comp = (
                    data.get("openconfig-platform:components", {})
                    .get("component", [{}])[0]
                )
                info["model"] = (
                    comp.get("state", {})
                    .get("icx-openconfig-platform-aug:switch-model", "")
                )
        except FastIronError:
            pass
        return info

    async def get_platform_status(self) -> FastIronPlatformStatus | None:
        """Retourne température, état PSU et ventilateurs depuis le switch."""
        try:
            data = await self._request(
                "GET", "/data/openconfig-platform:components"
            )
        except FastIronError:
            return None
        if not data:
            return None

        comp = (
            data.get("openconfig-platform:components", {})
            .get("component", [{}])[0]
        )
        status = FastIronPlatformStatus()

        # Température
        temp = comp.get("state", {}).get("temperature", {})
        val = temp.get(f"{_AUG}actual_temperature")
        status.temperature = float(val) if val is not None else None

        # Alimentations
        for key, raw in comp.get("power-supply", {}).get("state", {}).items():
            bare = key.replace(_AUG, "")
            if bare.startswith("power-supply-") and bare.endswith("-status"):
                idx_s = bare[len("power-supply-"):-len("-status")]
                if idx_s.isdigit():
                    text = str(raw).strip()
                    status.psu.append((int(idx_s), text, "ok" in text.lower()))
        status.psu.sort()

        # Ventilateurs
        for key, raw in comp.get("fan", {}).get("state", {}).items():
            bare = key.replace(_AUG, "")
            if bare.startswith("fan-") and bare.endswith("-status"):
                idx_s = bare[len("fan-"):-len("-status")]
                if idx_s.isdigit():
                    text = str(raw).strip()
                    status.fans.append((int(idx_s), text, "ok" in text.lower()))
        status.fans.sort()

        return status

    async def get_ports(self) -> list[FastIronPort]:
        """Retourne tous les ports Ethernet physiques du switch."""
        data = await self._request("GET", "/data/interfaces")
        if not data:
            return []
        return [
            FastIronPort(iface)
            for iface in _get_interfaces(data)
            if str(iface.get("name", "")).lower().startswith("ethernet")
        ]

    @staticmethod
    def _encode_port(port_id: str) -> str:
        return quote(port_id, safe="")

    async def set_port_admin_state(self, port_id: str, enabled: bool) -> None:
        """Active ou désactive l'état admin d'un port."""
        encoded = self._encode_port(port_id)
        await self._request(
            "PATCH",
            f"/data/interfaces/interface={encoded}/config",
            json={"config": {"enabled": enabled}},
        )

    async def set_port_poe(self, port_id: str, enabled: bool) -> None:
        """Active ou désactive le PoE sur un port."""
        encoded = self._encode_port(port_id)
        await self._request(
            "PATCH",
            f"/data/interfaces/interface={encoded}/ethernet/poe/config",
            json={"config": {"enabled": enabled}},
        )

    async def reboot(self) -> None:
        """Redémarre le switch sur la partition flash primaire."""
        await self._request(
            "POST",
            "/operations/boot-sys-flash",
            json={"icx-openconfig-platform-aug:input": {"primary": [None]}},
        )

    async def close(self) -> None:
        """Ferme la session HTTP."""
        if self._session and not self._session.closed:
            await self._session.close()
