"""INVITADO: catálogo público y prueba temporal con reserva EXCLUSIVA de una
unidad de exhibición. Al expirar, cerrar sesión o perder la conexión, el
servidor envía DETENER y libera la reserva."""
import asyncio
import time

from fastapi import APIRouter, Depends, HTTPException, Request

from app.config import settings
from app.database import consultar, ejecutar, transaccion
from app.schemas import SesionInvitadoRequest
from app.seguridad import (
    INVITADO, Principal, auditar, control_exclusivo, expira_en, limite_tasa, nuevo_token, requiere_sesion,
)
from app.websocket_manager import manager

router = APIRouter(prefix="/api/v1", tags=["Catálogo e Invitados"])

_ultima_conexion: dict[int, float] = {}   # id_sesion -> último instante con WSS conectado


@router.get("/catalogo", summary="Catálogo público: modelos y unidades de exhibición (sin datos privados)")
def catalogo():
    modelos = consultar("""SELECT id_modelo, nombre, descripcion, microcontrolador, imagen
                             FROM modelos WHERE activo = 1 AND publicado = 1 ORDER BY nombre""")
    unidades = consultar("""SELECT v.id_vehiculo, v.id_modelo, v.numero_serie,
                                   (SELECT COUNT(*) FROM sesiones s WHERE s.id_vehiculo = v.id_vehiculo
                                      AND s.tipo = 'INVITADO' AND s.cerrada IS NULL
                                      AND s.expira > UTC_TIMESTAMP()) AS reservas
                              FROM vehiculos v
                             WHERE v.estado_comercial = 'EXHIBICION' AND v.activo = 1""")
    capacidades = consultar("""SELECT v.id_modelo, c.nombre, c.permitido_invitado
                                 FROM comandos c JOIN vehiculos v ON v.id_vehiculo = c.id_vehiculo
                                WHERE c.activo = 1 AND v.id_vehiculo = (SELECT MIN(v2.id_vehiculo) FROM vehiculos v2
                                                                         WHERE v2.id_modelo = v.id_modelo)""")
    for m in modelos:
        m["capacidades"] = sorted({c["nombre"] for c in capacidades if c["id_modelo"] == m["id_modelo"]})
        m["comandos_invitado"] = sorted({c["nombre"] for c in capacidades
                                         if c["id_modelo"] == m["id_modelo"] and c["permitido_invitado"]})
        m["exhibicion"] = [{
            "id_vehiculo": u["id_vehiculo"], "numero_serie": u["numero_serie"],
            "estado": "OCUPADA" if u["reservas"] or control_exclusivo.ocupado_por(u["id_vehiculo"]) else "LIBRE",
            "conectada": manager.dispositivo_conectado(u["id_vehiculo"]),
        } for u in unidades if u["id_modelo"] == m["id_modelo"]]
    return {"modelos": modelos, "minutos_prueba": settings.INVITADO_MINUTOS}


@router.post("/invitado/sesiones", status_code=201, summary="Solicitar prueba temporal de una unidad de exhibición")
def crear_sesion_invitado(datos: SesionInvitadoRequest, request: Request):
    ip = request.client.host if request.client else "?"
    limite_tasa.verificar(f"invitado:{ip}", 5, 300, "Demasiadas solicitudes de prueba. Espera unos minutos.")
    alias = (datos.alias or "Invitado").strip()[:60] or "Invitado"
    token, token_hash = nuevo_token()
    expira = expira_en(minutos=settings.INVITADO_MINUTOS)
    with transaccion() as conn:
        cur = conn.cursor(dictionary=True)
        # Bloquea la fila de la unidad: dos solicitudes simultáneas no pueden reservarla
        cur.execute("""SELECT id_vehiculo, estado_comercial, activo FROM vehiculos
                        WHERE id_vehiculo = %s FOR UPDATE""", (datos.id_vehiculo,))
        v = cur.fetchone()
        if not v or not v["activo"] or v["estado_comercial"] != "EXHIBICION":
            raise HTTPException(404, "Unidad de exhibición no disponible")
        cur.execute("""SELECT COUNT(*) AS n FROM sesiones WHERE id_vehiculo = %s AND tipo = 'INVITADO'
                        AND cerrada IS NULL AND expira > UTC_TIMESTAMP()""", (datos.id_vehiculo,))
        if cur.fetchone()["n"] or control_exclusivo.ocupado_por(datos.id_vehiculo):
            raise HTTPException(409, "La unidad está ocupada por otra persona. Intenta en unos minutos.")
        cur.execute("""INSERT INTO sesiones (token_hash, tipo, id_vehiculo, alias, expira)
                       VALUES (%s, 'INVITADO', %s, %s, %s)""", (token_hash, datos.id_vehiculo, alias, expira))
        id_sesion = cur.lastrowid
        cur.close()
    _ultima_conexion[id_sesion] = time.monotonic()
    p = Principal(INVITADO, id_sesion, nombre=alias, id_vehiculo_reservado=datos.id_vehiculo)
    auditar(p, "INICIO_PRUEBA_INVITADO", "vehiculo", datos.id_vehiculo, "EXITO", f"{settings.INVITADO_MINUTOS} min")
    comandos = consultar("""SELECT id_comando, nombre, codigo FROM comandos
                             WHERE id_vehiculo = %s AND activo = 1 AND permitido_invitado = 1 ORDER BY codigo""",
                         (datos.id_vehiculo,))
    return {"token": token, "tipo": "Bearer", "id_vehiculo": datos.id_vehiculo, "expira": expira.isoformat(),
            "segundos": settings.INVITADO_MINUTOS * 60, "comandos_permitidos": comandos}


@router.delete("/invitado/sesiones/actual", summary="Terminar la prueba (detiene la unidad y libera la reserva)")
async def terminar_sesion_invitado(p: Principal = Depends(requiere_sesion)):
    if p.tipo != INVITADO:
        raise HTTPException(403, "Solo para sesiones de invitado")
    await finalizar_reserva(p.id_sesion, p.id_vehiculo_reservado, "CERRADA_POR_INVITADO")
    return {"mensaje": "Prueba terminada; la unidad se detuvo y quedó libre"}


async def finalizar_reserva(id_sesion: int, id_vehiculo: int, motivo: str):
    ejecutar("""UPDATE sesiones SET cerrada = UTC_TIMESTAMP(), motivo_cierre = %s
                 WHERE id_sesion = %s AND cerrada IS NULL""", (motivo, id_sesion))
    _ultima_conexion.pop(id_sesion, None)
    from app.services import vehicle_service
    # Detención segura: solo si esta sesión era la que controlaba o tenía la reserva
    await vehicle_service.detener_sistema(id_vehiculo, f"SISTEMA:{motivo}"[:30])
    control_exclusivo.liberar(id_vehiculo, id_sesion)
    await manager.broadcast_to_vehicle(id_vehiculo, {"evento": "PRUEBA_INVITADO_FIN", "id_vehiculo": id_vehiculo,
                                                     "motivo": motivo})
    await manager.revocar_sesion(id_sesion, f"Prueba finalizada ({motivo})")
    auditar(Principal(INVITADO, id_sesion, nombre="Invitado", id_vehiculo_reservado=id_vehiculo),
            "FIN_PRUEBA_INVITADO", "vehiculo", id_vehiculo, "EXITO", motivo)


async def cerrar_reservas_de_unidad(id_vehiculo: int, motivo: str):
    for s in consultar("""SELECT id_sesion FROM sesiones WHERE id_vehiculo = %s AND tipo = 'INVITADO'
                           AND cerrada IS NULL""", (id_vehiculo,)):
        await finalizar_reserva(s["id_sesion"], id_vehiculo, motivo)


async def vigilante_invitados():
    """Tarea de fondo: cierra pruebas vencidas o sin WebSocket (pérdida de conexión).
    La consulta corre en otro hilo para que, si RDS tarda, la API siga respondiendo."""
    await asyncio.sleep(5)
    while True:
        try:
            activas = await asyncio.to_thread(consultar, """SELECT id_sesion, id_vehiculo, (expira <= UTC_TIMESTAMP()) AS vencida
                                     FROM sesiones WHERE tipo = 'INVITADO' AND cerrada IS NULL""")
            ahora = time.monotonic()
            for s in activas:
                if manager.sesion_conectada(s["id_sesion"]):
                    _ultima_conexion[s["id_sesion"]] = ahora
                if s["vencida"]:
                    await finalizar_reserva(s["id_sesion"], s["id_vehiculo"], "EXPIRADA")
                elif ahora - _ultima_conexion.setdefault(s["id_sesion"], ahora) > settings.INVITADO_GRACIA_SEG:
                    await finalizar_reserva(s["id_sesion"], s["id_vehiculo"], "SIN_CONEXION")
        except Exception as e:
            print("vigilante_invitados:", e)
        await asyncio.sleep(3)
