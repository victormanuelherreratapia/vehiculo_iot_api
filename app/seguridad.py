"""
Autenticación, autorización por rol + recurso (vehículo) y auditoría.

- Contraseñas: PBKDF2-SHA256 con sal (biblioteca estándar).
- Tokens: aleatorios (secrets); en RDS solo se guarda su SHA-256.
- Nunca se confía en rol, id_usuario ni id_vehiculo enviados por el navegador:
  todo se obtiene de la sesión guardada en RDS.
"""
import hashlib
import hmac
import secrets
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.config import settings
from app.database import consultar, ejecutar

ADMIN, USUARIO, INVITADO, MANTENIMIENTO = "ADMIN", "USUARIO", "INVITADO", "MANTENIMIENTO"
COD_DETENER = 9

esquema_bearer = HTTPBearer(auto_error=False, description="Token obtenido en /api/v1/auth/login")


def ahora_utc() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


# ---------------------------------------------------------------------
# Contraseñas y tokens
# ---------------------------------------------------------------------
def hash_password(clave: str) -> str:
    sal = secrets.token_hex(16)
    iteraciones = 390000
    dk = hashlib.pbkdf2_hmac("sha256", clave.encode(), bytes.fromhex(sal), iteraciones).hex()
    return f"pbkdf2_sha256${iteraciones}${sal}${dk}"


def verificar_password(clave: str, guardado: str) -> bool:
    try:
        _alg, iteraciones, sal, dk = guardado.split("$")
        calc = hashlib.pbkdf2_hmac("sha256", clave.encode(), bytes.fromhex(sal), int(iteraciones)).hex()
        return hmac.compare_digest(calc, dk)
    except (ValueError, AttributeError):
        return False


def nuevo_token() -> tuple[str, str]:
    token = secrets.token_urlsafe(32)
    return token, sha256(token)


def sha256(texto: str) -> str:
    return hashlib.sha256(texto.encode()).hexdigest()


# ---------------------------------------------------------------------
# Identidad de la petición
# ---------------------------------------------------------------------
@dataclass
class Principal:
    tipo: str                         # ADMIN | USUARIO | INVITADO | MANTENIMIENTO
    id_sesion: Optional[int] = None
    id_usuario: Optional[int] = None
    nombre: str = ""
    correo: str = ""
    id_vehiculo_reservado: Optional[int] = None   # solo Invitado
    expira: Optional[datetime] = None
    extra: dict = field(default_factory=dict)

    @property
    def actor(self) -> str:
        return self.correo or self.nombre or self.tipo

    @property
    def origen(self) -> str:
        """Texto guardado en historial_comandos.origen (máx. 30 caracteres)."""
        ident = self.id_usuario if self.id_usuario else self.id_sesion
        return f"WEB_{self.tipo}:{ident}"[:30]


def principal_desde_token(token: str) -> Optional[Principal]:
    if not token:
        return None
    fila = consultar(
        """SELECT s.id_sesion, s.tipo, s.id_usuario, s.id_vehiculo, s.alias, s.expira,
                  u.nombre, u.correo, u.activo, r.nombre AS rol
             FROM sesiones s
        LEFT JOIN usuarios u ON u.id_usuario = s.id_usuario
        LEFT JOIN roles r    ON r.id_rol = u.id_rol
            WHERE s.token_hash = %s AND s.cerrada IS NULL AND s.expira > UTC_TIMESTAMP()""",
        (sha256(token),), uno=True)
    if not fila:
        return None
    if fila["tipo"] == "INVITADO":
        return Principal(INVITADO, fila["id_sesion"], None, fila["alias"] or "Invitado", "",
                         fila["id_vehiculo"], fila["expira"])
    if not fila["activo"]:
        return None
    return Principal(fila["rol"], fila["id_sesion"], fila["id_usuario"], fila["nombre"], fila["correo"],
                     None, fila["expira"])


def principal_opcional(request: Request,
                       cred: Optional[HTTPAuthorizationCredentials] = Depends(esquema_bearer)) -> Optional[Principal]:
    if cred and cred.scheme.lower() == "bearer":
        p = principal_desde_token(cred.credentials)
        if p:
            return p
        raise HTTPException(401, "Sesión inválida o expirada. Inicia sesión de nuevo.")
    # Compatibilidad: clave de mantenimiento para Swagger/Thunder Client (solo servidor)
    clave = request.headers.get("x-api-key", "")
    if settings.API_KEY and clave and hmac.compare_digest(clave.encode(), settings.API_KEY.encode()):
        return Principal(MANTENIMIENTO, nombre="X-API-Key")
    return None


def requiere_sesion(p: Optional[Principal] = Depends(principal_opcional)) -> Principal:
    if not p:
        raise HTTPException(401, "Se requiere iniciar sesión.")
    return p


def requiere_cuenta(p: Principal = Depends(requiere_sesion)) -> Principal:
    if p.tipo not in (ADMIN, USUARIO):
        raise HTTPException(403, "Esta función requiere una cuenta de Administrador o Usuario.")
    return p


def requiere_admin(p: Principal = Depends(requiere_sesion)) -> Principal:
    if p.tipo not in (ADMIN, MANTENIMIENTO):
        auditar(p, "ACCESO_ADMIN", "admin", None, "RECHAZADO", "Intento de usar una ruta de administración")
        raise HTTPException(403, "Solo el Administrador puede realizar esta operación.")
    return p


def requiere_usuario(p: Principal = Depends(requiere_sesion)) -> Principal:
    if p.tipo != USUARIO:
        raise HTTPException(403, "Función exclusiva de clientes compradores.")
    return p


# ---------------------------------------------------------------------
# Autorización por VEHÍCULO (además del rol)
# ---------------------------------------------------------------------
def obtener_unidad(id_vehiculo: int) -> Optional[dict]:
    return consultar(
        """SELECT id_vehiculo, nombre, id_modelo, numero_serie, estado_comercial, id_propietario,
                  soporte_hasta, activo
             FROM vehiculos WHERE id_vehiculo = %s""", (id_vehiculo,), uno=True)


def autorizar_vehiculo(p: Principal, id_vehiculo: int, accion: str = "operar") -> dict:
    """Comprueba que la sesión pueda operar o monitorear ESTA unidad.

    - USUARIO: solo unidades propias (estado VENDIDO). Si no es suya -> 404
      (no se revela que la unidad existe).
    - INVITADO: solo la unidad de exhibición que tiene reservada.
    - ADMIN: unidades de la empresa (DISPONIBLE / EXHIBICION). Una unidad
      vendida solo con consentimiento de soporte vigente (soporte_hasta).
    """
    u = obtener_unidad(id_vehiculo)
    if not u or not u["activo"] or u["estado_comercial"] == "INACTIVO":
        raise HTTPException(404, "Vehículo no encontrado")

    if p.tipo == USUARIO:
        if u["id_propietario"] != p.id_usuario or u["estado_comercial"] != "VENDIDO":
            auditar(p, f"{accion.upper()}_AJENO", "vehiculo", id_vehiculo, "RECHAZADO", "Unidad no asignada al usuario")
            raise HTTPException(404, "Vehículo no encontrado")
        return u

    if p.tipo == INVITADO:
        if p.id_vehiculo_reservado != id_vehiculo or u["estado_comercial"] != "EXHIBICION":
            auditar(p, f"{accion.upper()}_AJENO", "vehiculo", id_vehiculo, "RECHAZADO", "Fuera de la reserva del invitado")
            raise HTTPException(403, "Tu sesión de invitado solo permite la unidad de exhibición reservada.")
        return u

    if p.tipo in (ADMIN, MANTENIMIENTO):
        # La clave de mantenimiento tiene las mismas restricciones que el Administrador
        if u["estado_comercial"] == "VENDIDO":
            if not u["soporte_hasta"] or u["soporte_hasta"] <= ahora_utc():
                auditar(p, f"{accion.upper()}_SIN_CONSENTIMIENTO", "vehiculo", id_vehiculo, "RECHAZADO",
                        "Unidad vendida sin autorización de soporte")
                raise HTTPException(403, "Unidad vendida: se requiere autorización de soporte del comprador.")
        return u

    raise HTTPException(403, "Sin permiso.")


# ---------------------------------------------------------------------
# Exclusividad de control y límite de peticiones (memoria del proceso)
# ---------------------------------------------------------------------
class ControlExclusivo:
    """Solo una sesión mueve una unidad a la vez. DETENER siempre se permite."""

    def __init__(self):
        self._duenos: dict[int, tuple[int, float]] = {}
        self._candado = threading.Lock()

    def tomar(self, id_vehiculo: int, id_sesion: Optional[int], es_detener: bool):
        if id_sesion is None:
            return
        with self._candado:
            actual = self._duenos.get(id_vehiculo)
            libre = not actual or actual[1] < time.monotonic() or actual[0] == id_sesion
            if not libre and not es_detener:
                raise HTTPException(409, "Otra sesión está controlando este vehículo. Espera unos segundos.")
            if libre:
                self._duenos[id_vehiculo] = (id_sesion, time.monotonic() + settings.BLOQUEO_CONTROL_SEG)

    def liberar(self, id_vehiculo: int, id_sesion: Optional[int] = None):
        with self._candado:
            actual = self._duenos.get(id_vehiculo)
            if actual and (id_sesion is None or actual[0] == id_sesion):
                self._duenos.pop(id_vehiculo, None)

    def ocupado_por(self, id_vehiculo: int) -> Optional[int]:
        actual = self._duenos.get(id_vehiculo)
        return actual[0] if actual and actual[1] >= time.monotonic() else None


control_exclusivo = ControlExclusivo()


class LimiteTasa:
    def __init__(self):
        self._marcas: dict[str, list[float]] = {}
        self._candado = threading.Lock()

    def verificar(self, clave: str, maximo: int, ventana_seg: float, mensaje: str):
        ahora = time.monotonic()
        with self._candado:
            marcas = [t for t in self._marcas.get(clave, []) if ahora - t < ventana_seg]
            if len(marcas) >= maximo:
                self._marcas[clave] = marcas
                raise HTTPException(429, mensaje)
            marcas.append(ahora)
            self._marcas[clave] = marcas


limite_tasa = LimiteTasa()


# ---------------------------------------------------------------------
# Auditoría (sin contraseñas ni tokens)
# ---------------------------------------------------------------------
def auditar(p: Optional[Principal], accion: str, recurso: str, id_recurso, resultado: str, detalle: str = ""):
    try:
        ejecutar(
            """INSERT INTO auditoria (id_usuario, actor, rol, accion, recurso, id_recurso, resultado, detalle)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
            (p.id_usuario if p else None, (p.actor if p else "anónimo")[:120], (p.tipo if p else "ANONIMO")[:20],
             accion[:60], recurso[:40], None if id_recurso is None else str(id_recurso)[:40], resultado,
             (detalle or "")[:255]))
    except Exception as e:   # la auditoría nunca debe tumbar la operación
        print("No se pudo registrar auditoría:", e)


def expira_en(horas: int = 0, minutos: int = 0) -> datetime:
    return ahora_utc() + timedelta(hours=horas, minutes=minutos)
