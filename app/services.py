import asyncio
from datetime import datetime

from fastapi import HTTPException

from app.config import settings
from app.database import db_manager, consultar
from app.repositories import IoTRepository
from app.seguridad import (
    ADMIN, INVITADO, MANTENIMIENTO, USUARIO, COD_DETENER,
    Principal, auditar, autorizar_vehiculo, control_exclusivo, limite_tasa,
)
from app.websocket_manager import manager


class VehicleService:
    def __init__(self):
        self.repo = IoTRepository()
        # id_vehiculo -> (tarea asyncio de la DEMO, id_sesion que la inició)
        self.tareas_demo: dict[int, tuple] = {}

    def _catalogo_comandos(self, id_vehiculo: int) -> dict:
        return {c['id_comando']: c for c in self.repo.obtener_comandos_vehiculo(id_vehiculo)}

    # ------------------------------------------------------------------
    # Movimiento individual (CONTROL)
    # ------------------------------------------------------------------
    async def ejecutar_movimiento_individual(self, p: Principal, id_vehiculo: int, id_comando: int):
        autorizar_vehiculo(p, id_vehiculo, "operar")
        limite_tasa.verificar(f"mov:{p.id_sesion or p.tipo}", settings.MAX_COMANDOS_POR_SEG, 1.0,
                              "Demasiados comandos por segundo.")

        comandos = self.repo.obtener_comandos_vehiculo(id_vehiculo)
        comando_valido = next((c for c in comandos if c['id_comando'] == id_comando and c.get('activo')), None)
        if not comando_valido:
            raise HTTPException(status_code=400, detail="El comando no pertenece al vehículo o está inactivo")

        es_detener = int(comando_valido.get('codigo')) == COD_DETENER
        if p.tipo == INVITADO and not comando_valido.get('permitido_invitado'):
            auditar(p, "COMANDO_NO_PERMITIDO", "comando", id_comando, "RECHAZADO", comando_valido.get('nombre'))
            raise HTTPException(403, "Ese comando no está habilitado para la prueba de invitado.")

        # Exclusividad: solo una sesión mueve la unidad; DETENER siempre pasa
        control_exclusivo.tomar(id_vehiculo, p.id_sesion, es_detener)

        # DETENER tiene prioridad: cancela la DEMO en curso
        if es_detener and id_vehiculo in self.tareas_demo:
            self.tareas_demo[id_vehiculo][0].cancel()

        conn = db_manager.get_connection()
        try:
            conn.start_transaction()
            self.repo.actualizar_estado(id_vehiculo, id_comando, conn=conn)
            self.repo.registrar_historial(id_vehiculo, id_comando, p.origen, conn=conn)
            conn.commit()
        except Exception as e:
            conn.rollback()
            raise HTTPException(status_code=500, detail=f"Error en la transacción: {str(e)}")
        finally:
            conn.close()

        evento = {
            "evento": "MOVIMIENTO_INDIVIDUAL",
            "id_vehiculo": id_vehiculo,
            "id_comando": id_comando,
            "comando": comando_valido.get('nombre'),
            "codigo_comando": comando_valido.get('codigo'),
            "timestamp": datetime.utcnow().isoformat()
        }
        await manager.broadcast_to_vehicle(id_vehiculo, evento)
        return {"mensaje": "Movimiento individual ejecutado correctamente", "evento": evento}

    async def detener_sistema(self, id_vehiculo: int, origen: str):
        """Detención segura iniciada por el servidor (expiración o cierre de sesión)."""
        comando = next((c for c in self.repo.obtener_comandos_vehiculo(id_vehiculo)
                        if int(c['codigo']) == COD_DETENER), None)
        if id_vehiculo in self.tareas_demo:
            self.tareas_demo[id_vehiculo][0].cancel()
        if not comando:
            return
        try:
            self.repo.actualizar_estado(id_vehiculo, comando['id_comando'])
            self.repo.registrar_historial(id_vehiculo, comando['id_comando'], origen)
        except Exception as e:
            print("No se pudo registrar la detención:", e)
        await manager.broadcast_to_vehicle(id_vehiculo, {
            "evento": "MOVIMIENTO_INDIVIDUAL", "id_vehiculo": id_vehiculo, "id_comando": comando['id_comando'],
            "comando": comando['nombre'], "codigo_comando": comando['codigo'],
            "timestamp": datetime.utcnow().isoformat(), "origen": origen,
        })

    # ------------------------------------------------------------------
    # DEMO
    # ------------------------------------------------------------------
    def demo_visible(self, p: Principal, demo: dict) -> bool:
        if not demo or not demo.get('activo'):
            return False
        if demo.get('tipo') == 'FABRICA':
            return True
        return p.tipo == USUARIO and demo.get('id_propietario') == p.id_usuario

    async def ejecutar_demo(self, p: Principal, id_vehiculo: int, id_demo: int):
        autorizar_vehiculo(p, id_vehiculo, "operar")
        if id_vehiculo in self.tareas_demo:
            raise HTTPException(status_code=409, detail="Ya existe una DEMO en ejecución para este vehículo")

        demo = consultar("SELECT * FROM demos WHERE id_demo = %s AND id_vehiculo = %s", (id_demo, id_vehiculo), uno=True)
        if not self.demo_visible(p, demo):
            raise HTTPException(404, "DEMO no encontrada para este vehículo")

        movimientos = self.repo.obtener_movimientos_demo(id_demo)
        if not movimientos:
            raise HTTPException(status_code=404, detail="La DEMO no contiene movimientos registrados")
        movimientos = sorted(movimientos, key=lambda m: m['orden'])
        catalogo = self._catalogo_comandos(id_vehiculo)

        # Validación en servidor: comandos de ESTA unidad, activos y límites seguros
        total = 0
        for m in movimientos:
            c = catalogo.get(m['id_comando'])
            if not c or not c.get('activo'):
                raise HTTPException(422, f"El paso {m['orden']} usa un comando no válido para esta unidad")
            if p.tipo == INVITADO and not c.get('permitido_invitado'):
                raise HTTPException(403, "Esta DEMO usa comandos no habilitados para invitados")
            dur = min(int(m['duracion_ms']), settings.DEMO_MAX_MS)
            total += dur + min(int(m['pausa_ms']), settings.DEMO_MAX_PAUSA_MS)
        if total > settings.DEMO_MAX_TOTAL_MS:
            raise HTTPException(422, "La DEMO supera la duración máxima permitida")

        control_exclusivo.tomar(id_vehiculo, p.id_sesion, False)
        tarea = asyncio.create_task(self._procesar_demo_task(id_vehiculo, id_demo, movimientos, catalogo))
        self.tareas_demo[id_vehiculo] = (tarea, p.id_sesion)
        auditar(p, "EJECUTAR_DEMO", "demo", id_demo, "EXITO", f"vehículo {id_vehiculo}")
        return {
            "mensaje": "Ejecución de DEMO iniciada por WebSocket",
            "id_vehiculo": id_vehiculo,
            "id_demo": id_demo,
            "total_movimientos": len(movimientos)
        }

    async def cancelar_demo(self, p: Principal, id_vehiculo: int):
        autorizar_vehiculo(p, id_vehiculo, "operar")
        tarea = self.tareas_demo.get(id_vehiculo)
        if not tarea:
            raise HTTPException(status_code=404, detail="No hay una DEMO en ejecución para este vehículo")
        tarea[0].cancel()
        return {"mensaje": "Cancelación de DEMO solicitada", "id_vehiculo": id_vehiculo}

    async def _procesar_demo_task(self, id_vehiculo: int, id_demo: int, movimientos: list, catalogo: dict):
        ejecutados = 0
        try:
            await manager.broadcast_to_vehicle(id_vehiculo, {
                "evento": "DEMO_INICIO",
                "id_vehiculo": id_vehiculo,
                "id_demo": id_demo,
                "total_movimientos": len(movimientos),
                "timestamp": datetime.utcnow().isoformat()
            })

            for mov in movimientos:
                id_comando = mov['id_comando']
                duracion_ms = min(int(mov['duracion_ms']), settings.DEMO_MAX_MS)
                pausa_ms = min(int(mov['pausa_ms']), settings.DEMO_MAX_PAUSA_MS)
                comando = catalogo.get(id_comando, {})

                self.repo.actualizar_estado(id_vehiculo, id_comando)

                await manager.broadcast_to_vehicle(id_vehiculo, {
                    "evento": "DEMO_MOVIMIENTO",
                    "id_vehiculo": id_vehiculo,
                    "orden": mov['orden'],
                    "id_comando": id_comando,
                    "comando": comando.get('nombre'),
                    "codigo_comando": comando.get('codigo'),
                    "duracion_ms": duracion_ms,
                    "pausa_ms": pausa_ms,
                    "timestamp": datetime.utcnow().isoformat()
                })
                ejecutados += 1
                await asyncio.sleep((duracion_ms + pausa_ms) / 1000.0)

            await manager.broadcast_to_vehicle(id_vehiculo, {
                "evento": "DEMO_FIN",
                "id_vehiculo": id_vehiculo,
                "id_demo": id_demo,
                "movimientos_ejecutados": ejecutados,
                "timestamp": datetime.utcnow().isoformat()
            })

        except asyncio.CancelledError:
            await manager.broadcast_to_vehicle(id_vehiculo, {
                "evento": "DEMO_CANCELADA",
                "id_vehiculo": id_vehiculo,
                "id_demo": id_demo,
                "movimientos_ejecutados": ejecutados,
                "timestamp": datetime.utcnow().isoformat()
            })

        except Exception as e:
            await manager.broadcast_to_vehicle(id_vehiculo, {
                "evento": "DEMO_ERROR",
                "id_vehiculo": id_vehiculo,
                "id_demo": id_demo,
                "detalle": "Error interno al ejecutar la DEMO",
                "timestamp": datetime.utcnow().isoformat()
            })
            print("DEMO_ERROR:", e)

        finally:
            self.tareas_demo.pop(id_vehiculo, None)


vehicle_service = VehicleService()
