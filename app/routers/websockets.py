"""Canal WSS por vehículo, ahora autenticado y autorizado.

Navegador:  wss://.../ws/vehiculo/{id}?token=<token de la sesión>
ESP8266:    wss://.../ws/vehiculo/{id}?dispositivo=<clave del dispositivo>

Cada conexión se valida ANTES de aceptarla: identidad + permiso sobre ESA
unidad. CORS no protege WebSockets, por eso la validación es obligatoria.
"""
import hmac
from typing import Optional

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.encoders import jsonable_encoder

from app.config import settings
from app.database import consultar
from app.repositories import IoTRepository
from app.seguridad import auditar, autorizar_vehiculo, principal_desde_token, sha256
from app.websocket_manager import Conexion, manager

router = APIRouter(tags=["WebSocket Monitoreo"])
repo = IoTRepository()


def _es_dispositivo(id_vehiculo: int, clave: Optional[str]) -> bool:
    fila = consultar("SELECT dispositivo_hash FROM vehiculos WHERE id_vehiculo = %s AND activo = 1",
                     (id_vehiculo,), uno=True)
    if not fila:
        return False
    if clave and fila["dispositivo_hash"]:
        return hmac.compare_digest(sha256(clave), fila["dispositivo_hash"])
    return False


@router.websocket("/ws/vehiculo/{id_vehiculo}")
async def websocket_endpoint(websocket: WebSocket, id_vehiculo: int,
                             token: Optional[str] = None, dispositivo: Optional[str] = None):
    conexion = None
    try:
        if dispositivo is not None or (token is None and settings.WS_PERMITIR_SIN_CLAVE):
            if _es_dispositivo(id_vehiculo, dispositivo) or (dispositivo is None and settings.WS_PERMITIR_SIN_CLAVE):
                conexion = Conexion(websocket, "DISPOSITIVO")
        elif token:
            p = principal_desde_token(token)
            if p:
                autorizar_vehiculo(p, id_vehiculo, "suscribir_wss")
                conexion = Conexion(websocket, p.tipo, p.id_sesion, p.id_usuario)
    except HTTPException:
        conexion = None
    except Exception as e:
        print("WSS: error al validar:", e)
        conexion = None

    if conexion is None:
        # 1008 = violación de política: sin identidad válida o sin permiso para esta unidad
        await websocket.close(code=1008)
        return

    await websocket.accept()
    manager.registrar(id_vehiculo, conexion)
    try:
        estado_actual = repo.obtener_estado(id_vehiculo)
        await websocket.send_json({
            "evento": "CONEXION_ESTABLECIDA",
            "id_vehiculo": id_vehiculo,
            "rol": conexion.tipo,
            "estado_inicial": jsonable_encoder(estado_actual)
        })
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        manager.disconnect(websocket, id_vehiculo)
