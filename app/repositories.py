from app.database import db_manager

class IoTRepository:
    # --- VEHÍCULOS ---
    def crear_vehiculo(self, nombre: str, modelo: str, activo: bool):
        conn = db_manager.get_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.callproc('sp_crear_vehiculo', (nombre, modelo, activo))
        conn.commit()
        cursor.close()
        conn.close()

    def obtener_vehiculos(self):
        conn = db_manager.get_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.callproc('sp_obtener_vehiculos')
        result = [res.fetchall() for res in cursor.stored_results()][0]
        cursor.close()
        conn.close()
        return result

    def obtener_vehiculo(self, id_vehiculo: int):
        conn = db_manager.get_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.callproc('sp_obtener_vehiculo', (id_vehiculo,))
        res = [r.fetchall() for r in cursor.stored_results()][0]
        cursor.close()
        conn.close()
        return res[0] if res else None

    def actualizar_vehiculo(self, id_vehiculo: int, nombre: str, modelo: str, activo: bool):
        conn = db_manager.get_connection()
        cursor = conn.cursor()
        cursor.callproc('sp_actualizar_vehiculo', (id_vehiculo, nombre, modelo, activo))
        conn.commit()
        cursor.close()
        conn.close()

    def eliminar_vehiculo(self, id_vehiculo: int):
        conn = db_manager.get_connection()
        cursor = conn.cursor()
        cursor.callproc('sp_eliminar_vehiculo', (id_vehiculo,))
        conn.commit()
        cursor.close()
        conn.close()

    # --- COMANDOS ---
    def crear_comando(self, id_vehiculo: int, nombre: str, codigo: str, desc: str, activo: bool):
        conn = db_manager.get_connection()
        cursor = conn.cursor()
        cursor.callproc('sp_crear_comando', (id_vehiculo, nombre, codigo, desc, activo))
        conn.commit()
        cursor.close()
        conn.close()

    def obtener_comandos_vehiculo(self, id_vehiculo: int):
        conn = db_manager.get_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.callproc('sp_obtener_comandos_vehiculo', (id_vehiculo,))
        res = [r.fetchall() for r in cursor.stored_results()][0]
        cursor.close()
        conn.close()
        return res

    def actualizar_comando(self, id_comando: int, nombre: str, codigo: str, desc: str, activo: bool):
        conn = db_manager.get_connection()
        cursor = conn.cursor()
        cursor.callproc('sp_actualizar_comando', (id_comando, nombre, codigo, desc, activo))
        conn.commit()
        cursor.close()
        conn.close()

    def eliminar_comando(self, id_comando: int):
        conn = db_manager.get_connection()
        cursor = conn.cursor()
        cursor.callproc('sp_eliminar_comando', (id_comando,))
        conn.commit()
        cursor.close()
        conn.close()

    # --- ESTADO ---
    def actualizar_estado(self, id_vehiculo: int, id_comando: int, conn=None):
        local_conn = False
        if conn is None:
            conn = db_manager.get_connection()
            local_conn = True
        cursor = conn.cursor()
        # Se envían los 3 parámetros requeridos por el Stored Procedure
        cursor.callproc('sp_actualizar_estado', (id_vehiculo, id_comando, 1))
        if local_conn:
            conn.commit()
            cursor.close()
            conn.close()

    def obtener_estado(self, id_vehiculo: int):
        conn = db_manager.get_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.callproc('sp_obtener_estado', (id_vehiculo,))
        res = [r.fetchall() for r in cursor.stored_results()][0]
        cursor.close()
        conn.close()
        return res[0] if res else None

    # --- HISTORIAL ---
    def registrar_historial(self, id_vehiculo: int, id_comando: int, origen: str, conn=None):
        local_conn = False
        if conn is None:
            conn = db_manager.get_connection()
            local_conn = True
        cursor = conn.cursor()
        cursor.callproc('sp_registrar_historial', (id_vehiculo, id_comando, origen))
        if local_conn:
            conn.commit()
            cursor.close()
            conn.close()

    def obtener_historial(self, id_vehiculo: int):
        conn = db_manager.get_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.callproc('sp_obtener_historial', (id_vehiculo,))
        res = [r.fetchall() for r in cursor.stored_results()][0]
        cursor.close()
        conn.close()
        return res[:10]

    # --- DEMO ---
    def crear_demo(self, id_vehiculo: int, nombre: str, desc: str, activa: bool):
        conn = db_manager.get_connection()
        cursor = conn.cursor()
        cursor.callproc('sp_crear_demo', (id_vehiculo, nombre, desc, activa))
        conn.commit()
        cursor.close()
        conn.close()

    def obtener_demos(self, id_vehiculo: int):
        conn = db_manager.get_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.callproc('sp_obtener_demos', (id_vehiculo,))
        res = [r.fetchall() for r in cursor.stored_results()][0]
        cursor.close()
        conn.close()
        return res

    def actualizar_demo(self, id_demo: int, nombre: str, desc: str, activa: bool):
        conn = db_manager.get_connection()
        cursor = conn.cursor()
        cursor.callproc('sp_actualizar_demo', (id_demo, nombre, desc, activa))
        conn.commit()
        cursor.close()
        conn.close()

    def eliminar_demo(self, id_demo: int):
        conn = db_manager.get_connection()
        cursor = conn.cursor()
        cursor.callproc('sp_eliminar_demo', (id_demo,))
        conn.commit()
        cursor.close()
        conn.close()

    # --- MOVIMIENTOS DEMO ---
    def agregar_movimiento_demo(self, id_demo: int, id_comando: int, orden: int, duracion: int, pausa: int):
        conn = db_manager.get_connection()
        cursor = conn.cursor()
        cursor.callproc('sp_agregar_movimiento_demo', (id_demo, id_comando, orden, duracion, pausa))
        conn.commit()
        cursor.close()
        conn.close()

    def obtener_movimientos_demo(self, id_demo: int):
        conn = db_manager.get_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.callproc('sp_obtener_movimientos_demo', (id_demo,))
        res = [r.fetchall() for r in cursor.stored_results()][0]
        cursor.close()
        conn.close()
        return res

    def actualizar_movimiento_demo(self, id_mov: int, orden: int, duracion: int, pausa: int):
        conn = db_manager.get_connection()
        cursor = conn.cursor()
        cursor.callproc('sp_actualizar_movimiento_demo', (id_mov, orden, duracion, pausa))
        conn.commit()
        cursor.close()
        conn.close()

    def eliminar_movimiento_demo(self, id_mov: int):
        conn = db_manager.get_connection()
        cursor = conn.cursor()
        cursor.callproc('sp_eliminar_movimiento_demo', (id_mov,))
        conn.commit()
        cursor.close()
        conn.close()