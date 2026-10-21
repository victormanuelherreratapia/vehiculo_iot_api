from fastapi import WebSocket
from typing import Dict, List


class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[int, List[WebSocket]] = {}

    async def connect(self, websocket: WebSocket, id_vehiculo: int):
        await websocket.accept()
        if id_vehiculo not in self.active_connections:
            self.active_connections[id_vehiculo] = []
        self.active_connections[id_vehiculo].append(websocket)

    def disconnect(self, websocket: WebSocket, id_vehiculo: int):
        if id_vehiculo in self.active_connections:
            if websocket in self.active_connections[id_vehiculo]:
                self.active_connections[id_vehiculo].remove(websocket)
            if not self.active_connections[id_vehiculo]:
                del self.active_connections[id_vehiculo]

    async def broadcast_to_vehicle(self, id_vehiculo: int, message: dict):
        # Se recorre una copia y se descartan las conexiones caídas
        for connection in list(self.active_connections.get(id_vehiculo, [])):
            try:
                await connection.send_json(message)
            except Exception:
                self.disconnect(connection, id_vehiculo)


manager = ConnectionManager()
