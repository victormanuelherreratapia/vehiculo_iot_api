from fastapi import APIRouter, HTTPException
from app.schemas import (
    VehiculoCreate, VehiculoUpdate, ComandoCreate, ComandoUpdate,
    MovimientoIndividualRequest, DemoCreate, DemoUpdate,
    MovimientoDemoCreate, MovimientoDemoUpdate
)
from app.repositories import IoTRepository
from app.services import vehicle_service

router = APIRouter(prefix="/api/v1", tags=["Vehículos IoT"])
repo = IoTRepository()

@router.post("/vehiculos", status_code=201, summary="SP: sp_crear_vehiculo")
def crear_vehiculo(datos: VehiculoCreate):
    repo.crear_vehiculo(datos.nombre, datos.modelo, datos.activo)
    return {"mensaje": "Vehículo creado con éxito"}

@router.get("/vehiculos", summary="SP: sp_obtener_vehiculos")
def obtener_vehiculos():
    return repo.obtener_vehiculos()

@router.get("/vehiculos/{id_vehiculo}", summary="SP: sp_obtener_vehiculo")
def obtener_vehiculo(id_vehiculo: int):
    v = repo.obtener_vehiculo(id_vehiculo)
    if not v:
        raise HTTPException(status_code=404, detail="Vehículo no encontrado")
    return v

@router.post("/vehiculos/{id_vehiculo}/actualizar", summary="SP: sp_actualizar_vehiculo")
def actualizar_vehiculo(id_vehiculo: int, datos: VehiculoUpdate):
    repo.actualizar_vehiculo(id_vehiculo, datos.nombre or "", datos.modelo or "", datos.activo if datos.activo is not None else True)
    return {"mensaje": "Vehículo actualizado"}

@router.post("/vehiculos/{id_vehiculo}/eliminar", summary="SP: sp_eliminar_vehiculo")
def eliminar_vehiculo(id_vehiculo: int):
    repo.eliminar_vehiculo(id_vehiculo)
    return {"mensaje": "Vehículo eliminado"}

@router.post("/comandos", status_code=201, summary="SP: sp_crear_comando")
def crear_comando(datos: ComandoCreate):
    repo.crear_comando(datos.id_vehiculo, datos.nombre_comando, datos.codigo_comando, datos.descripcion or "", datos.activo)
    return {"mensaje": "Comando creado"}

@router.get("/vehiculos/{id_vehiculo}/comandos", summary="SP: sp_obtener_comandos_vehiculo")
def obtener_comandos(id_vehiculo: int):
    return repo.obtener_comandos_vehiculo(id_vehiculo)

@router.post("/comandos/{id_comando}/actualizar", summary="SP: sp_actualizar_comando")
def actualizar_comando(id_comando: int, datos: ComandoUpdate):
    repo.actualizar_comando(id_comando, datos.nombre_comando or "", datos.codigo_comando or "", datos.descripcion or "", datos.activo if datos.activo is not None else True)
    return {"mensaje": "Comando actualizado"}

@router.post("/comandos/{id_comando}/eliminar", summary="SP: sp_eliminar_comando")
def eliminar_comando(id_comando: int):
    repo.eliminar_comando(id_comando)
    return {"mensaje": "Comando eliminado"}

@router.post("/movimientos/individual", summary="SP: sp_actualizar_estado + sp_registrar_historial")
async def movimiento_individual(req: MovimientoIndividualRequest):
    return await vehicle_service.ejecutar_movimiento_individual(req.id_vehiculo, req.id_comando, req.origen)

@router.get("/vehiculos/{id_vehiculo}/estado", summary="SP: sp_obtener_estado")
def obtener_estado(id_vehiculo: int):
    est = repo.obtener_estado(id_vehiculo)
    if not est:
        raise HTTPException(status_code=404, detail="Estado no encontrado")
    return est

@router.get("/vehiculos/{id_vehiculo}/historial", summary="SP: sp_obtener_historial (Máx 10)")
def obtener_historial(id_vehiculo: int):
    return repo.obtener_historial(id_vehiculo)

@router.post("/demos", status_code=201, summary="SP: sp_crear_demo")
def crear_demo(datos: DemoCreate):
    repo.crear_demo(datos.id_vehiculo, datos.nombre_demo, datos.descripcion or "", datos.activa)
    return {"mensaje": "Demo creada"}

@router.get("/vehiculos/{id_vehiculo}/demos", summary="SP: sp_obtener_demos")
def obtener_demos(id_vehiculo: int):
    return repo.obtener_demos(id_vehiculo)

@router.post("/demos/{id_demo}/actualizar", summary="SP: sp_actualizar_demo")
def actualizar_demo(id_demo: int, datos: DemoUpdate):
    repo.actualizar_demo(id_demo, datos.nombre_demo or "", datos.descripcion or "", datos.activa if datos.activa is not None else True)
    return {"mensaje": "Demo actualizada"}

@router.post("/demos/{id_demo}/eliminar", summary="SP: sp_eliminar_demo")
def eliminar_demo(id_demo: int):
    repo.eliminar_demo(id_demo)
    return {"mensaje": "Demo eliminada"}

@router.post("/demos/movimientos", status_code=201, summary="SP: sp_agregar_movimiento_demo")
def agregar_movimiento_demo(datos: MovimientoDemoCreate):
    repo.agregar_movimiento_demo(datos.id_demo, datos.id_comando, datos.orden, datos.duracion_ms, datos.pausa_ms)
    return {"mensaje": "Movimiento agregado a la DEMO"}

@router.get("/demos/{id_demo}/movimientos", summary="SP: sp_obtener_movimientos_demo")
def obtener_movimientos_demo(id_demo: int):
    return repo.obtener_movimientos_demo(id_demo)

@router.post("/demos/movimientos/{id_movimiento}/actualizar", summary="SP: sp_actualizar_movimiento_demo")
def actualizar_movimiento_demo(id_movimiento: int, datos: MovimientoDemoUpdate):
    repo.actualizar_movimiento_demo(id_movimiento, datos.orden or 0, datos.duracion_ms or 0, datos.pausa_ms or 0)
    return {"mensaje": "Movimiento de demo actualizado"}

@router.post("/demos/movimientos/{id_movimiento}/eliminar", summary="SP: sp_eliminar_movimiento_demo")
def eliminar_movimiento_demo(id_movimiento: int):
    repo.eliminar_movimiento_demo(id_movimiento)
    return {"mensaje": "Movimiento de demo eliminado"}

@router.post("/vehiculos/{id_vehiculo}/demos/{id_demo}/iniciar", summary="Iniciar DEMO por WebSocket")
async def iniciar_demo(id_vehiculo: int, id_demo: int):
    return await vehicle_service.ejecutar_demo(id_vehiculo, id_demo)