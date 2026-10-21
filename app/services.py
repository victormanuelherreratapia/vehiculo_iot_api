import asyncio
from datetime import datetime
from fastapi import HTTPException
from app.repositories import IoTRepository
from app.database import db_manager
from app.websocket_manager import manager


class VehicleService:
    def __init__(self):
        self.repo = IoTRepository()
        # id_vehiculo -> tarea asyncio de la DEMO en ejecución
        self.tareas_demo: dict[int, asyncio.Task] = {}

    def _catalogo_comandos(self, id_vehiculo: int) -> dict:
        return {c['id_comando']: c for c in self.repo.obtener_comandos_vehiculo(id_vehiculo)}

    async def ejecutar_movimiento_individual(self, id_vehiculo: int, id_comando: int, origen: str):
        vehiculo = self.repo.obtener_vehiculo(id_vehiculo)
        if not vehiculo or not vehiculo.get('activo'):
            raise HTTPException(status_code=400, detail="El vehículo no existe o está inactivo")

        comandos = self.repo.obtener_comandos_vehiculo(id_vehiculo)
        comando_valido = next(
            (c for c in comandos if c['id_comando'] == id_comando and c.get('activo')), None
        )
        if not comando_valido:
            raise HTTPException(status_code=400, detail="El comando no pertenece al vehículo o está inactivo")

        conn = db_manager.get_connection()
        try:
            conn.start_transaction()
            self.repo.actualizar_estado(id_vehiculo, id_comando, conn=conn)
            self.repo.registrar_historial(id_vehiculo, id_comando, origen, conn=conn)
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
            "timestamp": datetime.now().isoformat()
        }
        await manager.broadcast_to_vehicle(id_vehiculo, evento)
        return {"mensaje": "Movimiento individual ejecutado correctamente", "evento": evento}

    async def ejecutar_demo(self, id_vehiculo: int, id_demo: int):
        if id_vehiculo in self.tareas_demo:
            raise HTTPException(status_code=409, detail="Ya existe una DEMO en ejecución para este vehículo")

        movimientos = self.repo.obtener_movimientos_demo(id_demo)
        if not movimientos:
            raise HTTPException(status_code=404, detail="La DEMO no contiene movimientos registrados")

        movimientos = sorted(movimientos, key=lambda m: m['orden'])
        catalogo = self._catalogo_comandos(id_vehiculo)

        tarea = asyncio.create_task(
            self._procesar_demo_task(id_vehiculo, id_demo, movimientos, catalogo)
        )
        self.tareas_demo[id_vehiculo] = tarea
        return {
            "mensaje": "Ejecución de DEMO iniciada por WebSocket",
            "id_vehiculo": id_vehiculo,
            "id_demo": id_demo,
            "total_movimientos": len(movimientos)
        }

    async def cancelar_demo(self, id_vehiculo: int):
        tarea = self.tareas_demo.get(id_vehiculo)
        if not tarea:
            raise HTTPException(status_code=404, detail="No hay una DEMO en ejecución para este vehículo")
        tarea.cancel()
        return {"mensaje": "Cancelación de DEMO solicitada", "id_vehiculo": id_vehiculo}

    async def _procesar_demo_task(self, id_vehiculo: int, id_demo: int, movimientos: list, catalogo: dict):
        ejecutados = 0
        try:
            await manager.broadcast_to_vehicle(id_vehiculo, {
                "evento": "DEMO_INICIO",
                "id_vehiculo": id_vehiculo,
                "id_demo": id_demo,
                "total_movimientos": len(movimientos),
                "timestamp": datetime.now().isoformat()
            })

            for mov in movimientos:
                id_comando = mov['id_comando']
                duracion_s = mov['duracion_ms'] / 1000.0
                pausa_s = mov['pausa_ms'] / 1000.0
                comando = catalogo.get(id_comando, {})

                self.repo.actualizar_estado(id_vehiculo, id_comando)

                await manager.broadcast_to_vehicle(id_vehiculo, {
                    "evento": "DEMO_MOVIMIENTO",
                    "id_vehiculo": id_vehiculo,
                    "orden": mov['orden'],
                    "id_comando": id_comando,
                    "comando": comando.get('nombre'),
                    "codigo_comando": comando.get('codigo'),
                    "duracion_ms": mov['duracion_ms'],
                    "pausa_ms": mov['pausa_ms'],
                    "timestamp": datetime.now().isoformat()
                })
                ejecutados += 1

                await asyncio.sleep(duracion_s + pausa_s)

            await manager.broadcast_to_vehicle(id_vehiculo, {
                "evento": "DEMO_FIN",
                "id_vehiculo": id_vehiculo,
                "id_demo": id_demo,
                "movimientos_ejecutados": ejecutados,
                "timestamp": datetime.now().isoformat()
            })

        except asyncio.CancelledError:
            await manager.broadcast_to_vehicle(id_vehiculo, {
                "evento": "DEMO_CANCELADA",
                "id_vehiculo": id_vehiculo,
                "id_demo": id_demo,
                "movimientos_ejecutados": ejecutados,
                "timestamp": datetime.now().isoformat()
            })

        except Exception as e:
            await manager.broadcast_to_vehicle(id_vehiculo, {
                "evento": "DEMO_ERROR",
                "id_vehiculo": id_vehiculo,
                "id_demo": id_demo,
                "detalle": str(e),
                "timestamp": datetime.now().isoformat()
            })

        finally:
            self.tareas_demo.pop(id_vehiculo, None)


vehicle_service = VehicleService()
