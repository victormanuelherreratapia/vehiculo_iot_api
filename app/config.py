import os
from dotenv import load_dotenv

load_dotenv()


def _int(nombre: str, defecto: int) -> int:
    try:
        return int(os.getenv(nombre, defecto))
    except ValueError:
        return defecto


class Config:
    # --- Base de datos (solo en el servidor, archivo .env) ---
    DB_HOST: str = os.getenv("DB_HOST", "localhost")
    DB_USER: str = os.getenv("DB_USER", "root")
    DB_PASSWORD: str = os.getenv("DB_PASSWORD", "")
    DB_NAME: str = os.getenv("DB_NAME", "vehiculo_iot")
    DB_PORT: int = _int("DB_PORT", 3306)

    # Clave de mantenimiento heredada (Swagger / Thunder Client). Opcional.
    API_KEY: str = os.getenv("API_KEY", "")

    # --- Sesiones ---
    SESION_HORAS: int = _int("SESION_HORAS", 8)              # cuentas Admin / Usuario
    INVITADO_MINUTOS: int = _int("INVITADO_MINUTOS", 5)      # prueba temporal del Invitado
    INVITADO_GRACIA_SEG: int = _int("INVITADO_GRACIA_SEG", 20)  # sin WebSocket => se cierra
    SOPORTE_MAX_MIN: int = _int("SOPORTE_MAX_MIN", 120)      # consentimiento de soporte

    # --- Seguridad física ---
    BLOQUEO_CONTROL_SEG: int = _int("BLOQUEO_CONTROL_SEG", 15)  # exclusividad de control
    MAX_COMANDOS_POR_SEG: int = _int("MAX_COMANDOS_POR_SEG", 8)
    DEMO_MAX_PASOS: int = _int("DEMO_MAX_PASOS", 20)
    DEMO_MIN_MS: int = _int("DEMO_MIN_MS", 100)
    DEMO_MAX_MS: int = _int("DEMO_MAX_MS", 5000)
    DEMO_MAX_PAUSA_MS: int = _int("DEMO_MAX_PAUSA_MS", 3000)
    DEMO_MAX_TOTAL_MS: int = _int("DEMO_MAX_TOTAL_MS", 60000)

    # Mientras el ESP8266 no tenga su clave de dispositivo se puede permitir
    # temporalmente su conexión sin clave (0 = NO, recomendado).
    WS_PERMITIR_SIN_CLAVE: bool = os.getenv("WS_PERMITIR_SIN_CLAVE", "0") == "1"


settings = Config()
