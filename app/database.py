import mysql.connector
from mysql.connector import pooling, Error
from app.config import settings

class DatabaseConnectionManager:
    def __init__(self):
        try:
            self.pool = mysql.connector.pooling.MySQLConnectionPool(
                pool_name="iot_pool",
                pool_size=5,
                host=settings.DB_HOST,
                user=settings.DB_USER,
                password=settings.DB_PASSWORD,
                database=settings.DB_NAME,
                port=settings.DB_PORT
            )
        except Error as e:
            print(f"Error al conectar con RDS MySQL: {e}")
            raise e

    def get_connection(self):
        return self.pool.get_connection()

db_manager = DatabaseConnectionManager()