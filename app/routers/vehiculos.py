"""Las 21 APIs originales, ahora con autenticación y autorización por vehículo.

- Consultas de una unidad (vehículo, comandos, estado, historial, demos):
  solo quien puede operar/monitorear ESA unidad.
- Altas/cambios/bajas: solo Administrador (o la X-API-Key de mantenimiento).
- Eliminar vehículo: ahora es baja lógica (antes borraba el historial).
"""
from fastapi import APIRouter, Depends, HTTPException

from app.database import consultar, ejecutar
from app.repositories import IoTRepository
from app.schemas import (
    ComandoCreate, ComandoUpdate, DemoCreate, DemoUpdate, MovimientoDemoCreate, MovimientoDemoUpdate,
    MovimientoIndividualRequest, VehiculoCreate, VehiculoUpdate,
)
from app.seguridad import Principal, auditar, autorizar_vehiculo, requiere_admin, requiere_sesion
from app.services import vehicle_service

router = APIRouter(prefix="/api/v1", tags=["Vehículos IoT"])
repo = IoTRepository()


def _demo_editable(p: Principal, id_demo: int) -> dict:
    demo = consultar("SELECT * FROM demos WHERE id_demo = %s", (id_demo,), uno=True)
    if not demo:
        raise HTTPException(404, "DEMO no encontrada")
    if p.tipo != "MANTENIMIENTO" and demo["tipo"] != "FABRICA":
        raise HTTPException(403, "El Administrador solo edita demos de fábrica.")
    return demo


@router.post("/vehiculos", status_code=201, summary="Obsoleta en 4.3: usar POST /api/v1/admin/unidades (Admin)")
def crear_vehiculo(datos: VehiculoCreate, p: Principal = Depends(requiere_admin)):
    # Desde la migración V001 toda unidad necesita modelo y número de serie únicos;
    # sp_crear_vehiculo no los recibe, por eso el alta se hace en /admin/unidades.
    raise HTTPException(409, "Las unidades se registran con POST /api/v1/admin/unidades (requieren modelo y número de serie).")


@router.get("/vehiculos", summary="SP: sp_obtener_vehiculos (Admin)")
def obtener_vehiculos(p: Principal = Depends(requiere_admin)):
    vehiculos = repo.obtener_vehiculos()
    for v in vehiculos:
        v.pop("dispositivo_hash", None)
    return vehiculos


@router.get("/vehiculos/{id_vehiculo}", summary="SP: sp_obtener_vehiculo")
def obtener_vehiculo(id_vehiculo: int, p: Principal = Depends(requiere_sesion)):
    autorizar_vehiculo(p, id_vehiculo, "consultar")
    v = repo.obtener_vehiculo(id_vehiculo)
    if not v:
        raise HTTPException(status_code=404, detail="Vehículo no encontrado")
    v.pop("dispositivo_hash", None)
    return v


@router.post("/vehiculos/{id_vehiculo}/actualizar", summary="SP: sp_actualizar_vehiculo (Admin)")
def actualizar_vehiculo(id_vehiculo: int, datos: VehiculoUpdate, p: Principal = Depends(requiere_admin)):
    v = repo.obtener_vehiculo(id_vehiculo)
    if not v:
        raise HTTPException(404, "Vehículo no encontrado")
    repo.actualizar_vehiculo(
        id_vehiculo, datos.nombre or v["nombre"], datos.modelo or v["modelo"],
        datos.descripcion if datos.descripcion is not None else v["descripcion"],
        datos.microcontrolador or v["microcontrolador"],
        datos.activo if datos.activo is not None else bool(v["activo"]))
    auditar(p, "ACTUALIZAR_VEHICULO", "vehiculo", id_vehiculo, "EXITO")
    return {"mensaje": "Vehículo actualizado"}


@router.post("/vehiculos/{id_vehiculo}/eliminar", summary="Baja lógica del vehículo (Admin)")
def eliminar_vehiculo(id_vehiculo: int, p: Principal = Depends(requiere_admin)):
    v = repo.obtener_vehiculo(id_vehiculo)
    if not v:
        raise HTTPException(404, "Vehículo no encontrado")
    if v.get("estado_comercial") == "VENDIDO":
        raise HTTPException(409, "No se puede dar de baja una unidad vendida; primero retira la asignación.")
    ejecutar("UPDATE vehiculos SET activo = 0, estado_comercial = 'INACTIVO' WHERE id_vehiculo = %s", (id_vehiculo,))
    auditar(p, "BAJA_VEHICULO", "vehiculo", id_vehiculo, "EXITO", "Baja lógica (se conserva el historial)")
    return {"mensaje": "Vehículo dado de baja (baja lógica, el historial se conserva)"}


@router.post("/comandos", status_code=201, summary="SP: sp_crear_comando (Admin)")
def crear_comando(datos: ComandoCreate, p: Principal = Depends(requiere_admin)):
    r = repo.crear_comando(datos.id_vehiculo, datos.nombre_comando.strip().upper(), datos.codigo_comando,
                           datos.descripcion or "")
    auditar(p, "CREAR_COMANDO", "comando", (r or {}).get("id_comando"), "EXITO", datos.nombre_comando)
    return {"mensaje": "Comando creado", **(r or {})}


@router.get("/vehiculos/{id_vehiculo}/comandos", summary="SP: sp_obtener_comandos_vehiculo")
def obtener_comandos(id_vehiculo: int, p: Principal = Depends(requiere_sesion)):
    autorizar_vehiculo(p, id_vehiculo, "consultar")
    comandos = repo.obtener_comandos_vehiculo(id_vehiculo)
    if p.tipo == "INVITADO":
        comandos = [c for c in comandos if c.get("permitido_invitado")]
    return comandos


@router.post("/comandos/{id_comando}/actualizar", summary="SP: sp_actualizar_comando (Admin)")
def actualizar_comando(id_comando: int, datos: ComandoUpdate, p: Principal = Depends(requiere_admin)):
    c = consultar("SELECT * FROM comandos WHERE id_comando = %s", (id_comando,), uno=True)
    if not c:
        raise HTTPException(404, "Comando no encontrado")
    repo.actualizar_comando(
        id_comando, (datos.nombre_comando or c["nombre"]).upper(),
        datos.codigo_comando if datos.codigo_comando is not None else c["codigo"],
        datos.descripcion if datos.descripcion is not None else (c["descripcion"] or ""),
        datos.activo if datos.activo is not None else bool(c["activo"]))
    auditar(p, "ACTUALIZAR_COMANDO", "comando", id_comando, "EXITO")
    return {"mensaje": "Comando actualizado"}


@router.post("/comandos/{id_comando}/eliminar", summary="Desactivar comando (Admin)")
def eliminar_comando(id_comando: int, p: Principal = Depends(requiere_admin)):
    # Baja lógica: un comando usado en el historial o en demos no se borra
    ejecutar("UPDATE comandos SET activo = 0 WHERE id_comando = %s", (id_comando,))
    auditar(p, "DESACTIVAR_COMANDO", "comando", id_comando, "EXITO")
    return {"mensaje": "Comando desactivado"}


@router.post("/movimientos/individual", summary="Enviar movimiento (sesión con permiso sobre la unidad)")
async def movimiento_individual(req: MovimientoIndividualRequest, p: Principal = Depends(requiere_sesion)):
    return await vehicle_service.ejecutar_movimiento_individual(p, req.id_vehiculo, req.id_comando)


@router.get("/vehiculos/{id_vehiculo}/estado", summary="SP: sp_obtener_estado")
def obtener_estado(id_vehiculo: int, p: Principal = Depends(requiere_sesion)):
    autorizar_vehiculo(p, id_vehiculo, "monitorear")
    est = repo.obtener_estado(id_vehiculo)
    if not est:
        raise HTTPException(status_code=404, detail="Estado no encontrado")
    return est


@router.get("/vehiculos/{id_vehiculo}/historial", summary="Últimos 10 movimientos individuales")
def obtener_historial(id_vehiculo: int, p: Principal = Depends(requiere_sesion)):
    autorizar_vehiculo(p, id_vehiculo, "monitorear")
    return repo.obtener_historial(id_vehiculo)


@router.post("/demos", status_code=201, summary="SP: sp_crear_demo (Admin, demo de fábrica)")
def crear_demo(datos: DemoCreate, p: Principal = Depends(requiere_admin)):
    r = repo.crear_demo(datos.id_vehiculo, datos.nombre_demo, datos.descripcion or "")
    auditar(p, "CREAR_DEMO", "demo", (r or {}).get("id_demo"), "EXITO", datos.nombre_demo)
    return {"mensaje": "Demo creada", **(r or {})}


@router.get("/vehiculos/{id_vehiculo}/demos", summary="Demos visibles: de fábrica + privadas propias")
def obtener_demos(id_vehiculo: int, p: Principal = Depends(requiere_sesion)):
    autorizar_vehiculo(p, id_vehiculo, "consultar")
    return [d for d in repo.obtener_demos(id_vehiculo) if vehicle_service.demo_visible(p, d)]


@router.post("/demos/{id_demo}/actualizar", summary="SP: sp_actualizar_demo (Admin)")
def actualizar_demo(id_demo: int, datos: DemoUpdate, p: Principal = Depends(requiere_admin)):
    d = _demo_editable(p, id_demo)
    repo.actualizar_demo(id_demo, datos.nombre_demo or d["nombre"],
                         datos.descripcion if datos.descripcion is not None else (d["descripcion"] or ""),
                         datos.activa if datos.activa is not None else bool(d["activo"]))
    auditar(p, "ACTUALIZAR_DEMO", "demo", id_demo, "EXITO")
    return {"mensaje": "Demo actualizada"}


@router.post("/demos/{id_demo}/eliminar", summary="Desactivar demo (Admin)")
def eliminar_demo(id_demo: int, p: Principal = Depends(requiere_admin)):
    _demo_editable(p, id_demo)
    ejecutar("UPDATE demos SET activo = 0 WHERE id_demo = %s", (id_demo,))
    auditar(p, "DESACTIVAR_DEMO", "demo", id_demo, "EXITO")
    return {"mensaje": "Demo desactivada"}


@router.post("/demos/movimientos", status_code=201, summary="SP: sp_agregar_movimiento_demo (Admin)")
def agregar_movimiento_demo(datos: MovimientoDemoCreate, p: Principal = Depends(requiere_admin)):
    _demo_editable(p, datos.id_demo)
    repo.agregar_movimiento_demo(datos.id_demo, datos.id_comando, datos.orden, datos.duracion_ms, datos.pausa_ms)
    auditar(p, "AGREGAR_PASO_DEMO", "demo", datos.id_demo, "EXITO")
    return {"mensaje": "Movimiento agregado a la DEMO"}


@router.get("/demos/{id_demo}/movimientos", summary="SP: sp_obtener_movimientos_demo")
def obtener_movimientos_demo(id_demo: int, p: Principal = Depends(requiere_sesion)):
    demo = consultar("SELECT * FROM demos WHERE id_demo = %s", (id_demo,), uno=True)
    if not demo or not vehicle_service.demo_visible(p, demo):
        raise HTTPException(404, "DEMO no encontrada")
    autorizar_vehiculo(p, demo["id_vehiculo"], "consultar")
    return repo.obtener_movimientos_demo(id_demo)


@router.post("/demos/movimientos/{id_movimiento}/actualizar", summary="SP: sp_actualizar_movimiento_demo (Admin)")
def actualizar_movimiento_demo(id_movimiento: int, datos: MovimientoDemoUpdate, p: Principal = Depends(requiere_admin)):
    m = consultar("SELECT * FROM demo_movimientos WHERE id_demo_movimiento = %s", (id_movimiento,), uno=True)
    if not m:
        raise HTTPException(404, "Paso no encontrado")
    _demo_editable(p, m["id_demo"])
    repo.actualizar_movimiento_demo(
        id_movimiento, datos.id_comando or m["id_comando"], datos.orden or m["orden"],
        datos.duracion_ms or m["duracion_ms"], datos.pausa_ms if datos.pausa_ms is not None else m["pausa_ms"])
    auditar(p, "ACTUALIZAR_PASO_DEMO", "demo", m["id_demo"], "EXITO")
    return {"mensaje": "Movimiento de demo actualizado"}


@router.post("/demos/movimientos/{id_movimiento}/eliminar", summary="SP: sp_eliminar_movimiento_demo (Admin)")
def eliminar_movimiento_demo(id_movimiento: int, p: Principal = Depends(requiere_admin)):
    m = consultar("SELECT * FROM demo_movimientos WHERE id_demo_movimiento = %s", (id_movimiento,), uno=True)
    if not m:
        raise HTTPException(404, "Paso no encontrado")
    _demo_editable(p, m["id_demo"])
    repo.eliminar_movimiento_demo(id_movimiento)
    auditar(p, "ELIMINAR_PASO_DEMO", "demo", m["id_demo"], "EXITO")
    return {"mensaje": "Movimiento de demo eliminado"}


@router.post("/vehiculos/{id_vehiculo}/demos/{id_demo}/iniciar", summary="Iniciar DEMO (notifica por WebSocket)")
async def iniciar_demo(id_vehiculo: int, id_demo: int, p: Principal = Depends(requiere_sesion)):
    return await vehicle_service.ejecutar_demo(p, id_vehiculo, id_demo)
