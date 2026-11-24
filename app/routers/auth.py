from fastapi import APIRouter, Depends, HTTPException, Request

from app.config import settings
from app.database import consultar, ejecutar
from app.schemas import LoginRequest
from app.seguridad import (
    Principal, auditar, expira_en, limite_tasa, nuevo_token, requiere_sesion, verificar_password,
)
from app.websocket_manager import manager

router = APIRouter(prefix="/api/v1/auth", tags=["Autenticación"])


@router.post("/login", summary="Iniciar sesión (Administrador o Usuario)")
def login(datos: LoginRequest, request: Request):
    correo = datos.correo.strip().lower()
    ip = request.client.host if request.client else "?"
    limite_tasa.verificar(f"login:{ip}", 10, 60, "Demasiados intentos. Espera un minuto.")
    limite_tasa.verificar(f"login:{correo}", 5, 60, "Demasiados intentos para esta cuenta. Espera un minuto.")

    u = consultar(
        """SELECT u.id_usuario, u.nombre, u.correo, u.password_hash, u.activo, r.nombre AS rol
             FROM usuarios u JOIN roles r ON r.id_rol = u.id_rol
            WHERE u.correo = %s""", (correo,), uno=True)
    if not u or not u["activo"] or not verificar_password(datos.password, u["password_hash"]):
        auditar(Principal("ANONIMO", correo=correo), "LOGIN", "sesion", None, "RECHAZADO", "Credenciales inválidas")
        # Mismo mensaje para correo inexistente o contraseña incorrecta
        raise HTTPException(401, "Correo o contraseña incorrectos.")

    token, token_hash = nuevo_token()
    expira = expira_en(horas=settings.SESION_HORAS)
    id_sesion = ejecutar(
        "INSERT INTO sesiones (token_hash, tipo, id_usuario, expira) VALUES (%s, 'USUARIO', %s, %s)",
        (token_hash, u["id_usuario"], expira))
    ejecutar("UPDATE usuarios SET ultimo_acceso = UTC_TIMESTAMP() WHERE id_usuario = %s", (u["id_usuario"],))
    p = Principal(u["rol"], id_sesion, u["id_usuario"], u["nombre"], u["correo"])
    auditar(p, "LOGIN", "sesion", id_sesion, "EXITO")
    return {
        "token": token,
        "tipo": "Bearer",
        "expira": expira.isoformat(),
        "usuario": {"id_usuario": u["id_usuario"], "nombre": u["nombre"], "correo": u["correo"], "rol": u["rol"]},
    }


@router.post("/logout", summary="Cerrar sesión (invalida el token)")
async def logout(p: Principal = Depends(requiere_sesion)):
    if p.id_sesion:
        ejecutar("UPDATE sesiones SET cerrada = UTC_TIMESTAMP(), motivo_cierre = 'LOGOUT' WHERE id_sesion = %s",
                 (p.id_sesion,))
        await manager.revocar_sesion(p.id_sesion, "Sesión cerrada")
        if p.tipo == "INVITADO" and p.id_vehiculo_reservado:
            from app.routers.invitado import finalizar_reserva
            await finalizar_reserva(p.id_sesion, p.id_vehiculo_reservado, "CERRADA_POR_INVITADO")
    auditar(p, "LOGOUT", "sesion", p.id_sesion, "EXITO")
    return {"mensaje": "Sesión cerrada"}


@router.get("/yo", summary="Datos de la sesión actual")
def yo(p: Principal = Depends(requiere_sesion)):
    return {
        "tipo": p.tipo, "id_usuario": p.id_usuario, "nombre": p.nombre, "correo": p.correo,
        "id_vehiculo_reservado": p.id_vehiculo_reservado,
        "expira": p.expira.isoformat() if p.expira else None,
    }
