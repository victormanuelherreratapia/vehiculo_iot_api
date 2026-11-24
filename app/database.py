import threading
import time
from contextlib import contextmanager

import mysql.connector
from mysql.connector import pooling, Error

from app.config import settings


class DatabaseConnectionManager:
    """Pool de conexiones a RDS creado de forma perezosa.

    Antes el pool se creaba al importar el módulo: si RDS todavía no estaba
    lista al encender el Learner Lab, la API se cerraba con error. Ahora se
    crea en la primera consulta y se reintenta si RDS aún no responde.
    """

    def __init__(self):
        self._pool = None
        self._candado = threading.Lock()

    def _crear_pool(self):
        ultimo_error = None
        for intento in range(5):
            try:
                return mysql.connector.pooling.MySQLConnectionPool(
                    pool_name="iot_pool",
                    pool_size=8,
                    pool_reset_session=True,
                    host=settings.DB_HOST,
                    user=settings.DB_USER,
                    password=settings.DB_PASSWORD,
                    database=settings.DB_NAME,
                    port=settings.DB_PORT,
                    connection_timeout=10,
                )
            except Error as e:
                ultimo_error = e
                print(f"RDS no disponible (intento {intento + 1}/5): {e}")
                time.sleep(3)
        raise ultimo_error

    def get_connection(self):
        if self._pool is None:
            with self._candado:
                if self._pool is None:
                    self._pool = self._crear_pool()
        return self._pool.get_connection()


db_manager = DatabaseConnectionManager()


@contextmanager
def transaccion():
    """Conexión con commit al terminar o rollback si hay error."""
    conn = db_manager.get_connection()
    try:
        conn.start_transaction()
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def consultar(sql: str, params: tuple = (), uno: bool = False):
    """SELECT parametrizado (nunca se concatena texto del usuario en el SQL)."""
    conn = db_manager.get_connection()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute(sql, params)
        filas = cur.fetchall()
        cur.close()
        return (filas[0] if filas else None) if uno else filas
    finally:
        conn.close()


def ejecutar(sql: str, params: tuple = ()) -> int:
    """INSERT/UPDATE parametrizado con commit; devuelve lastrowid."""
    conn = db_manager.get_connection()
    try:
        cur = conn.cursor()
        cur.execute(sql, params)
        conn.commit()
        ultimo = cur.lastrowid
        cur.close()
        return ultimo
    finally:
        conn.close()
