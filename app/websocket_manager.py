from dataclasses import dataclass
from typing import Callable, Dict, List, Optional

from fastapi import WebSocket


@dataclass
class Conexion:
    websocket: WebSocket
    tipo: str                       # ADMIN | USUARIO | INVITADO | DISPOSITIVO
    id_sesion: Optional[int] = None
    id_usuario: Optional[int] = None


class ConnectionManager:
    """Canales WSS por vehículo. Cada conexión ya fue autenticada y
    autorizada para ESE vehículo antes de registrarse."""

    def __init__(self):
        self.active_connections: Dict[int, List[Conexion]] = {}

    def registrar(self, id_vehiculo: int, conexion: Conexion):
        self.active_connections.setdefault(id_vehiculo, []).append(conexion)

    def disconnect(self, websocket: WebSocket, id_vehiculo: int):
        lista = self.active_connections.get(id_vehiculo, [])
        self.active_connections[id_vehiculo] = [c for c in lista if c.websocket is not websocket]
        if not self.active_connections[id_vehiculo]:
            del self.active_connections[id_vehiculo]

    async def broadcast_to_vehicle(self, id_vehiculo: int, message: dict):
        # Se recorre una copia y se descartan las conexiones caídas
        for c in list(self.active_connections.get(id_vehiculo, [])):
            try:
                await c.websocket.send_json(message)
            except Exception:
                self.disconnect(c.websocket, id_vehiculo)

    async def revocar(self, id_vehiculo: int, quitar: Callable[[Conexion], bool], motivo: str):
        """Cierra las suscripciones que ya no tienen permiso (cambio de dueño, logout, expiración)."""
        for c in list(self.active_connections.get(id_vehiculo, [])):
            if quitar(c):
                try:
                    await c.websocket.send_json({"evento": "ACCESO_REVOCADO", "id_vehiculo": id_vehiculo, "motivo": motivo})
                    await c.websocket.close(code=4403)
                except Exception:
                    pass
                self.disconnect(c.websocket, id_vehiculo)

    async def revocar_sesion(self, id_sesion: int, motivo: str):
        for id_vehiculo in list(self.active_connections.keys()):
            await self.revocar(id_vehiculo, lambda c: c.id_sesion == id_sesion, motivo)

    def sesion_conectada(self, id_sesion: int) -> bool:
        return any(c.id_sesion == id_sesion for lista in self.active_connections.values() for c in lista)

    def dispositivo_conectado(self, id_vehiculo: int) -> bool:
        return any(c.tipo == "DISPOSITIVO" for c in self.active_connections.get(id_vehiculo, []))


manager = ConnectionManager()
