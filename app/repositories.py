from app.database import db_manager


class IoTRepository:
    """Acceso a los procedimientos almacenados originales (prácticas 2.x–4.2).

    Se corrigieron las llamadas cuyo número de parámetros no coincidía con
    el procedimiento real de RDS (crear/actualizar vehículo, crear comando,
    crear demo y actualizar paso de demo), que respondían error 500.
    """

    def _llamar(self, sp: str, args: tuple = (), devuelve: bool = False, uno: bool = False, conn=None):
        propia = conn is None
        conn = conn or db_manager.get_connection()
        try:
            cursor = conn.cursor(dictionary=True)
            cursor.callproc(sp, args)
            filas = []
            for r in cursor.stored_results():
                filas = r.fetchall()
            if propia:
                conn.commit()
            cursor.close()
        finally:
            if propia:
                conn.close()
        if not devuelve:
            return filas
        return (filas[0] if filas else None) if uno else filas

    # --- VEHÍCULOS ---
    def crear_vehiculo(self, nombre: str, modelo: str, descripcion: str, microcontrolador: str):
        return self._llamar('sp_crear_vehiculo', (nombre, modelo, descripcion, microcontrolador), True, True)

    def obtener_vehiculos(self):
        return self._llamar('sp_obtener_vehiculos', (), True)

    def obtener_vehiculo(self, id_vehiculo: int):
        return self._llamar('sp_obtener_vehiculo', (id_vehiculo,), True, True)

    def actualizar_vehiculo(self, id_vehiculo: int, nombre: str, modelo: str, descripcion: str,
                            microcontrolador: str, activo: bool):
        self._llamar('sp_actualizar_vehiculo', (id_vehiculo, nombre, modelo, descripcion, microcontrolador, activo))

    # --- COMANDOS ---
    def crear_comando(self, id_vehiculo: int, nombre: str, codigo: int, desc: str):
        return self._llamar('sp_crear_comando', (id_vehiculo, nombre, codigo, desc), True, True)

    def obtener_comandos_vehiculo(self, id_vehiculo: int):
        return self._llamar('sp_obtener_comandos_vehiculo', (id_vehiculo,), True)

    def actualizar_comando(self, id_comando: int, nombre: str, codigo: int, desc: str, activo: bool):
        self._llamar('sp_actualizar_comando', (id_comando, nombre, codigo, desc, activo))

    def eliminar_comando(self, id_comando: int):
        self._llamar('sp_eliminar_comando', (id_comando,))

    # --- ESTADO ---
    def actualizar_estado(self, id_vehiculo: int, id_comando: int, conn=None):
        self._llamar('sp_actualizar_estado', (id_vehiculo, id_comando, 1), conn=conn)

    def obtener_estado(self, id_vehiculo: int):
        return self._llamar('sp_obtener_estado', (id_vehiculo,), True, True)

    # --- HISTORIAL ---
    def registrar_historial(self, id_vehiculo: int, id_comando: int, origen: str, conn=None):
        self._llamar('sp_registrar_historial', (id_vehiculo, id_comando, origen[:30]), conn=conn)

    def obtener_historial(self, id_vehiculo: int):
        # Consulta parametrizada con LIMIT: usa el índice idx_historial_vehiculo_fecha
        conn = db_manager.get_connection()
        try:
            cur = conn.cursor(dictionary=True)
            cur.execute(
                """SELECT h.id_historial, h.id_vehiculo, c.nombre AS comando, c.codigo,
                          h.fecha_hora, h.origen
                     FROM historial_comandos h
                LEFT JOIN comandos c ON c.id_comando = h.id_comando
                    WHERE h.id_vehiculo = %s
                 ORDER BY h.fecha_hora DESC, h.id_historial DESC
                    LIMIT 10""", (id_vehiculo,))
            filas = cur.fetchall()
            cur.close()
            return filas
        finally:
            conn.close()

    # --- DEMO ---
    def crear_demo(self, id_vehiculo: int, nombre: str, desc: str):
        return self._llamar('sp_crear_demo', (id_vehiculo, nombre, desc), True, True)

    def obtener_demos(self, id_vehiculo: int):
        return self._llamar('sp_obtener_demos', (id_vehiculo,), True)

    def actualizar_demo(self, id_demo: int, nombre: str, desc: str, activa: bool):
        self._llamar('sp_actualizar_demo', (id_demo, nombre, desc, activa))

    # --- MOVIMIENTOS DEMO ---
    def agregar_movimiento_demo(self, id_demo: int, id_comando: int, orden: int, duracion: int, pausa: int, conn=None):
        self._llamar('sp_agregar_movimiento_demo', (id_demo, id_comando, orden, duracion, pausa), conn=conn)

    def obtener_movimientos_demo(self, id_demo: int):
        return self._llamar('sp_obtener_movimientos_demo', (id_demo,), True)

    def actualizar_movimiento_demo(self, id_mov: int, id_comando: int, orden: int, duracion: int, pausa: int):
        self._llamar('sp_actualizar_movimiento_demo', (id_mov, id_comando, orden, duracion, pausa))

    def eliminar_movimiento_demo(self, id_mov: int):
        self._llamar('sp_eliminar_movimiento_demo', (id_mov,))
