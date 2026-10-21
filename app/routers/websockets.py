from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from fastapi.encoders import jsonable_encoder
from app.websocket_manager import manager
from app.repositories import IoTRepository

router = APIRouter(tags=["WebSocket Monitoreo"])
repo = IoTRepository()


@router.websocket("/ws/vehiculo/{id_vehiculo}")
async def websocket_endpoint(websocket: WebSocket, id_vehiculo: int):
    await manager.connect(websocket, id_vehiculo)
    try:
        estado_actual = repo.obtener_estado(id_vehiculo)
        await websocket.send_json({
            "evento": "CONEXION_ESTABLECIDA",
            "id_vehiculo": id_vehiculo,
            "estado_inicial": jsonable_encoder(estado_actual)
        })
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        manager.disconnect(websocket, id_vehiculo)
