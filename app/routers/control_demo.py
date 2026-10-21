from fastapi import APIRouter
from app.services import vehicle_service

router = APIRouter(prefix="/api/v1", tags=["Control de DEMO"])


@router.post(
    "/vehiculos/{id_vehiculo}/demos/cancelar",
    summary="Cancelar la DEMO en ejecución (se notifica por WebSocket)"
)
async def cancelar_demo(id_vehiculo: int):
    return await vehicle_service.cancelar_demo(id_vehiculo)
