"""«Mis vehículos», consentimiento de soporte y editor de demos."""
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException

from app.config import settings
from app.database import consultar, ejecutar, transaccion
from app.repositories import IoTRepository
from app.schemas import DemoEditor, SoporteRequest
from app.seguridad import (
    ADMIN, INVITADO, USUARIO, Principal, ahora_utc, auditar, autorizar_vehiculo, requiere_cuenta,
    requiere_sesion, requiere_usuario,
)
from app.services import vehicle_service

router = APIRouter(prefix="/api/v1", tags=["Mis vehículos y demos"])
repo = IoTRepository()
COD_DEMO_CONTROL = 12   # demo interna del juguete: no se permite dentro de otra demo


@router.get("/mis-vehiculos", summary="Unidades que la sesión puede operar y monitorear")
def mis_vehiculos(p: Principal = Depends(requiere_sesion)):
    base = """SELECT v.id_vehiculo, v.numero_serie, v.nombre, v.estado_comercial, v.soporte_hasta,
                     m.nombre AS modelo, m.microcontrolador
                FROM vehiculos v JOIN modelos m ON m.id_modelo = v.id_modelo
               WHERE v.activo = 1 AND """
    if p.tipo == USUARIO:
        return consultar(base + "v.id_propietario = %s AND v.estado_comercial = 'VENDIDO' ORDER BY v.id_vehiculo",
                         (p.id_usuario,))
    if p.tipo == INVITADO:
        return consultar(base + "v.id_vehiculo = %s AND v.estado_comercial = 'EXHIBICION'", (p.id_vehiculo_reservado,))
    if p.tipo == ADMIN:
        # Inventario de la empresa + unidades vendidas con soporte autorizado vigente
        return consultar(base + """(v.estado_comercial IN ('DISPONIBLE','EXHIBICION')
                                    OR (v.estado_comercial = 'VENDIDO' AND v.soporte_hasta > UTC_TIMESTAMP()))
                                   ORDER BY v.id_vehiculo""")
    return []


@router.post("/mis-vehiculos/{id_vehiculo}/soporte", summary="El comprador autoriza soporte del Administrador por N minutos")
def autorizar_soporte(id_vehiculo: int, datos: SoporteRequest, p: Principal = Depends(requiere_usuario)):
    autorizar_vehiculo(p, id_vehiculo, "autorizar_soporte")
    minutos = min(datos.minutos, settings.SOPORTE_MAX_MIN)
    hasta = ahora_utc() + timedelta(minutes=minutos)
    ejecutar("UPDATE vehiculos SET soporte_hasta = %s WHERE id_vehiculo = %s", (hasta, id_vehiculo))
    auditar(p, "AUTORIZAR_SOPORTE", "vehiculo", id_vehiculo, "EXITO", f"{minutos} min")
    return {"mensaje": f"Soporte autorizado por {minutos} minutos", "soporte_hasta": hasta.isoformat()}


@router.delete("/mis-vehiculos/{id_vehiculo}/soporte", summary="El comprador revoca el soporte")
def revocar_soporte(id_vehiculo: int, p: Principal = Depends(requiere_usuario)):
    autorizar_vehiculo(p, id_vehiculo, "revocar_soporte")
    ejecutar("UPDATE vehiculos SET soporte_hasta = NULL WHERE id_vehiculo = %s", (id_vehiculo,))
    auditar(p, "REVOCAR_SOPORTE", "vehiculo", id_vehiculo, "EXITO")
    return {"mensaje": "Soporte revocado"}


# ----------------------------------------------------------------- Editor de demos
def _validar_pasos(id_vehiculo: int, pasos) -> list:
    if not pasos:
        raise HTTPException(422, "La demo necesita al menos un paso")
    if len(pasos) > settings.DEMO_MAX_PASOS:
        raise HTTPException(422, f"Máximo {settings.DEMO_MAX_PASOS} pasos")
    comandos = {c["id_comando"]: c for c in repo.obtener_comandos_vehiculo(id_vehiculo)}
    total = 0
    for i, paso in enumerate(pasos, 1):
        c = comandos.get(paso.id_comando)
        if not c or not c["activo"]:
            raise HTTPException(422, f"Paso {i}: el comando no pertenece a esta unidad o está inactivo")
        if int(c["codigo"]) == COD_DEMO_CONTROL:
            raise HTTPException(422, f"Paso {i}: no se permite ejecutar la demo del control dentro de una demo")
        if not settings.DEMO_MIN_MS <= paso.duracion_ms <= settings.DEMO_MAX_MS:
            raise HTTPException(422, f"Paso {i}: la duración debe estar entre {settings.DEMO_MIN_MS} y {settings.DEMO_MAX_MS} ms")
        if not 0 <= paso.pausa_ms <= settings.DEMO_MAX_PAUSA_MS:
            raise HTTPException(422, f"Paso {i}: la pausa debe estar entre 0 y {settings.DEMO_MAX_PAUSA_MS} ms")
        total += paso.duracion_ms + paso.pausa_ms
    if total > settings.DEMO_MAX_TOTAL_MS:
        raise HTTPException(422, f"La demo dura {total} ms; el máximo es {settings.DEMO_MAX_TOTAL_MS} ms")
    return pasos


def _demo_propia(p: Principal, id_demo: int) -> dict:
    d = consultar("SELECT * FROM demos WHERE id_demo = %s AND activo = 1", (id_demo,), uno=True)
    if not d:
        raise HTTPException(404, "DEMO no encontrada")
    if p.tipo == USUARIO and (d["tipo"] != "PRIVADA" or d["id_propietario"] != p.id_usuario):
        auditar(p, "EDITAR_DEMO_AJENA", "demo", id_demo, "RECHAZADO")
        raise HTTPException(404, "DEMO no encontrada")       # no se revela la demo ajena
    if p.tipo == ADMIN and d["tipo"] != "FABRICA":
        raise HTTPException(403, "El Administrador no edita demos privadas de los compradores")
    autorizar_vehiculo(p, d["id_vehiculo"], "editar_demo")
    return d


def _guardar_pasos(cur, id_demo: int, pasos):
    cur.execute("DELETE FROM demo_movimientos WHERE id_demo = %s", (id_demo,))
    for orden, paso in enumerate(pasos, 1):
        cur.execute("""INSERT INTO demo_movimientos (id_demo, id_comando, orden, duracion_ms, pausa_ms)
                       VALUES (%s, %s, %s, %s, %s)""", (id_demo, paso.id_comando, orden, paso.duracion_ms, paso.pausa_ms))


@router.get("/demos/{id_demo}", summary="Encabezado y pasos de una demo visible")
def obtener_demo(id_demo: int, p: Principal = Depends(requiere_sesion)):
    d = consultar("SELECT * FROM demos WHERE id_demo = %s", (id_demo,), uno=True)
    if not d or not vehicle_service.demo_visible(p, d):
        raise HTTPException(404, "DEMO no encontrada")
    autorizar_vehiculo(p, d["id_vehiculo"], "consultar")
    pasos = repo.obtener_movimientos_demo(id_demo)
    editable = (p.tipo == USUARIO and d["tipo"] == "PRIVADA" and d["id_propietario"] == p.id_usuario) or \
               (p.tipo == ADMIN and d["tipo"] == "FABRICA")
    return {**d, "pasos": pasos, "editable": editable,
            "duracion_total_ms": sum(int(x["duracion_ms"]) + int(x["pausa_ms"]) for x in pasos)}


@router.post("/demos-editor", status_code=201, summary="Crear demo con pasos (Usuario: privada · Admin: de fábrica)")
def crear_demo_editor(datos: DemoEditor, p: Principal = Depends(requiere_cuenta)):
    autorizar_vehiculo(p, datos.id_vehiculo, "crear_demo")
    _validar_pasos(datos.id_vehiculo, datos.pasos)
    tipo = "PRIVADA" if p.tipo == USUARIO else "FABRICA"
    with transaccion() as conn:
        cur = conn.cursor()
        cur.execute("""INSERT INTO demos (id_vehiculo, nombre, descripcion, tipo, id_propietario)
                       VALUES (%s, %s, %s, %s, %s)""",
                    (datos.id_vehiculo, datos.nombre.strip(), datos.descripcion,
                     tipo, p.id_usuario if tipo == "PRIVADA" else None))
        id_demo = cur.lastrowid
        _guardar_pasos(cur, id_demo, datos.pasos)
        cur.close()
    auditar(p, "CREAR_DEMO", "demo", id_demo, "EXITO", f"{tipo} · {len(datos.pasos)} pasos")
    return {"mensaje": "Demo guardada", "id_demo": id_demo, "tipo": tipo}


@router.put("/demos-editor/{id_demo}", summary="Reemplazar encabezado y pasos de una demo propia")
def editar_demo_editor(id_demo: int, datos: DemoEditor, p: Principal = Depends(requiere_cuenta)):
    d = _demo_propia(p, id_demo)
    if datos.id_vehiculo != d["id_vehiculo"]:
        raise HTTPException(422, "No se puede mover una demo a otra unidad")
    if d["id_vehiculo"] in vehicle_service.tareas_demo:
        raise HTTPException(409, "No se puede editar mientras hay una DEMO en ejecución en la unidad")
    _validar_pasos(d["id_vehiculo"], datos.pasos)
    with transaccion() as conn:
        cur = conn.cursor()
        cur.execute("UPDATE demos SET nombre = %s, descripcion = %s WHERE id_demo = %s",
                    (datos.nombre.strip(), datos.descripcion, id_demo))
        _guardar_pasos(cur, id_demo, datos.pasos)
        cur.close()
    auditar(p, "EDITAR_DEMO", "demo", id_demo, "EXITO", f"{len(datos.pasos)} pasos")
    return {"mensaje": "Demo actualizada", "id_demo": id_demo}


@router.delete("/demos-editor/{id_demo}", summary="Desactivar demo propia (baja lógica)")
def desactivar_demo_editor(id_demo: int, p: Principal = Depends(requiere_cuenta)):
    _demo_propia(p, id_demo)
    ejecutar("UPDATE demos SET activo = 0 WHERE id_demo = %s", (id_demo,))
    auditar(p, "DESACTIVAR_DEMO", "demo", id_demo, "EXITO")
    return {"mensaje": "Demo desactivada"}
