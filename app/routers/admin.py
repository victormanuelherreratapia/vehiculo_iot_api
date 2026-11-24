"""ADMINISTRACIÓN (solo rol ADMIN): dashboard, clientes, modelos, unidades,
asignaciones, clave de dispositivo y auditoría."""
import re
import secrets
from typing import Optional

import mysql.connector
from fastapi import APIRouter, Depends, HTTPException, Query

from app.database import consultar, ejecutar, transaccion
from app.schemas import (
    AsignacionRequest, DesasignacionRequest, ModeloCreate, ModeloUpdate, UnidadCreate, UnidadUpdate,
    UsuarioCreate, UsuarioUpdate,
)
from app.seguridad import Principal, auditar, control_exclusivo, hash_password, requiere_admin, sha256
from app.websocket_manager import manager

router = APIRouter(prefix="/api/v1/admin", tags=["Administración"])

CORREO = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
ESTADOS_EDITABLES = {"DISPONIBLE", "EXHIBICION", "INACTIVO"}


def _duplicado(e: mysql.connector.Error, mensaje: str):
    if getattr(e, "errno", None) == 1062:
        raise HTTPException(409, mensaje)
    raise e


# ----------------------------------------------------------------- Dashboard
@router.get("/dashboard", summary="Métricas reales desde RDS")
def dashboard(p: Principal = Depends(requiere_admin)):
    unidades = consultar("""SELECT estado_comercial, COUNT(*) AS n FROM vehiculos GROUP BY estado_comercial""")
    por_estado = {u["estado_comercial"]: u["n"] for u in unidades}
    ids = [r["id_vehiculo"] for r in consultar("SELECT id_vehiculo FROM vehiculos WHERE activo = 1")]
    return {
        "modelos": consultar("SELECT COUNT(*) AS n FROM modelos WHERE activo = 1", uno=True)["n"],
        "unidades_total": sum(por_estado.values()),
        "unidades_por_estado": {e: por_estado.get(e, 0) for e in ("DISPONIBLE", "VENDIDO", "EXHIBICION", "INACTIVO")},
        "clientes": consultar("SELECT COUNT(*) AS n FROM usuarios WHERE id_rol = 2 AND activo = 1", uno=True)["n"],
        "demos_fabrica": consultar("SELECT COUNT(*) AS n FROM demos WHERE tipo='FABRICA' AND activo=1", uno=True)["n"],
        "demos_privadas": consultar("SELECT COUNT(*) AS n FROM demos WHERE tipo='PRIVADA' AND activo=1", uno=True)["n"],
        "invitados_activos": consultar(
            """SELECT COUNT(*) AS n FROM sesiones WHERE tipo='INVITADO' AND cerrada IS NULL
                AND expira > UTC_TIMESTAMP()""", uno=True)["n"],
        # Verificable: el ESP8266 conectado al WSS con su clave de dispositivo
        "dispositivos_conectados": sum(1 for i in ids if manager.dispositivo_conectado(i)),
        "movimientos_hoy": consultar(
            "SELECT COUNT(*) AS n FROM historial_comandos WHERE fecha_hora >= UTC_DATE()", uno=True)["n"],
    }


# ----------------------------------------------------------------- Clientes / usuarios
@router.get("/usuarios", summary="Listar clientes y administradores")
def listar_usuarios(rol: Optional[str] = Query(None, description="ADMIN o USUARIO"),
                    q: Optional[str] = Query(None, max_length=60), p: Principal = Depends(requiere_admin)):
    sql = """SELECT u.id_usuario, u.nombre, u.correo, u.telefono, u.activo, r.nombre AS rol,
                    u.fecha_registro, u.ultimo_acceso,
                    (SELECT COUNT(*) FROM vehiculos v WHERE v.id_propietario = u.id_usuario) AS unidades
               FROM usuarios u JOIN roles r ON r.id_rol = u.id_rol WHERE 1=1"""
    params = []
    if rol:
        sql += " AND r.nombre = %s"
        params.append(rol.upper())
    if q:
        sql += " AND (u.nombre LIKE %s OR u.correo LIKE %s)"
        params += [f"%{q}%", f"%{q}%"]
    return consultar(sql + " ORDER BY u.nombre", tuple(params))


@router.post("/usuarios", status_code=201, summary="Alta de cliente (USUARIO) o administrador")
def crear_usuario(datos: UsuarioCreate, p: Principal = Depends(requiere_admin)):
    correo = datos.correo.strip().lower()
    if not CORREO.match(correo):
        raise HTTPException(422, "Correo no válido")
    rol = datos.rol.upper()
    if rol not in ("USUARIO", "ADMIN"):
        raise HTTPException(422, "Rol no válido (USUARIO o ADMIN)")
    try:
        nuevo = ejecutar(
            """INSERT INTO usuarios (id_rol, nombre, correo, telefono, password_hash)
               VALUES ((SELECT id_rol FROM roles WHERE nombre = %s), %s, %s, %s, %s)""",
            (rol, datos.nombre.strip(), correo, datos.telefono, hash_password(datos.password)))
    except mysql.connector.Error as e:
        _duplicado(e, "Ya existe una cuenta con ese correo")
    auditar(p, "CREAR_USUARIO", "usuario", nuevo, "EXITO", f"{correo} ({rol})")
    return {"mensaje": "Cuenta creada", "id_usuario": nuevo}


@router.patch("/usuarios/{id_usuario}", summary="Editar, desactivar o cambiar contraseña de un cliente")
async def editar_usuario(id_usuario: int, datos: UsuarioUpdate, p: Principal = Depends(requiere_admin)):
    u = consultar("SELECT * FROM usuarios WHERE id_usuario = %s", (id_usuario,), uno=True)
    if not u:
        raise HTTPException(404, "Usuario no encontrado")
    if datos.activo is False and id_usuario == p.id_usuario:
        raise HTTPException(409, "No puedes desactivar tu propia cuenta")
    ejecutar(
        """UPDATE usuarios SET nombre = %s, telefono = %s, activo = %s, password_hash = %s
            WHERE id_usuario = %s""",
        (datos.nombre or u["nombre"], datos.telefono if datos.telefono is not None else u["telefono"],
         datos.activo if datos.activo is not None else u["activo"],
         hash_password(datos.password) if datos.password else u["password_hash"], id_usuario))
    if datos.activo is False or datos.password:
        # Revocación inmediata: cierra sus sesiones y sus suscripciones WSS
        sesiones = consultar("SELECT id_sesion FROM sesiones WHERE id_usuario = %s AND cerrada IS NULL", (id_usuario,))
        ejecutar("""UPDATE sesiones SET cerrada = UTC_TIMESTAMP(), motivo_cierre = 'REVOCADA_ADMIN'
                     WHERE id_usuario = %s AND cerrada IS NULL""", (id_usuario,))
        for s in sesiones:
            await manager.revocar_sesion(s["id_sesion"], "Cuenta modificada por el administrador")
    cambios = [k for k, v in (datos.model_dump() if hasattr(datos, "model_dump") else datos.dict()).items()
               if v is not None and k != "password"] + (["password"] if datos.password else [])
    auditar(p, "EDITAR_USUARIO", "usuario", id_usuario, "EXITO", ", ".join(cambios))
    return {"mensaje": "Usuario actualizado"}


# ----------------------------------------------------------------- Modelos
@router.get("/modelos", summary="Modelos comerciales")
def listar_modelos(p: Principal = Depends(requiere_admin)):
    return consultar("""SELECT m.*, (SELECT COUNT(*) FROM vehiculos v WHERE v.id_modelo = m.id_modelo) AS unidades
                          FROM modelos m ORDER BY m.nombre""")


@router.post("/modelos", status_code=201, summary="Alta de modelo comercial")
def crear_modelo(datos: ModeloCreate, p: Principal = Depends(requiere_admin)):
    try:
        nuevo = ejecutar(
            "INSERT INTO modelos (nombre, descripcion, microcontrolador, imagen, publicado) VALUES (%s,%s,%s,%s,%s)",
            (datos.nombre.strip(), datos.descripcion, datos.microcontrolador, datos.imagen, datos.publicado))
    except mysql.connector.Error as e:
        _duplicado(e, "Ya existe un modelo con ese nombre")
    auditar(p, "CREAR_MODELO", "modelo", nuevo, "EXITO", datos.nombre)
    return {"mensaje": "Modelo creado", "id_modelo": nuevo}


@router.patch("/modelos/{id_modelo}", summary="Editar o desactivar modelo")
def editar_modelo(id_modelo: int, datos: ModeloUpdate, p: Principal = Depends(requiere_admin)):
    m = consultar("SELECT * FROM modelos WHERE id_modelo = %s", (id_modelo,), uno=True)
    if not m:
        raise HTTPException(404, "Modelo no encontrado")
    nuevo = {**m, **{k: v for k, v in (datos.model_dump() if hasattr(datos, "model_dump") else datos.dict()).items()
                     if v is not None}}
    try:
        ejecutar("""UPDATE modelos SET nombre=%s, descripcion=%s, microcontrolador=%s, imagen=%s, publicado=%s, activo=%s
                     WHERE id_modelo=%s""",
                 (nuevo["nombre"], nuevo["descripcion"], nuevo["microcontrolador"], nuevo["imagen"],
                  nuevo["publicado"], nuevo["activo"], id_modelo))
    except mysql.connector.Error as e:
        _duplicado(e, "Ya existe un modelo con ese nombre")
    auditar(p, "EDITAR_MODELO", "modelo", id_modelo, "EXITO")
    return {"mensaje": "Modelo actualizado"}


# ----------------------------------------------------------------- Unidades
@router.get("/unidades", summary="Inventario de unidades físicas")
def listar_unidades(estado: Optional[str] = None, q: Optional[str] = Query(None, max_length=60),
                    p: Principal = Depends(requiere_admin)):
    sql = """SELECT v.id_vehiculo, v.numero_serie, v.nombre, v.estado_comercial, v.activo, v.soporte_hasta,
                    m.id_modelo, m.nombre AS modelo, u.id_usuario AS id_propietario, u.nombre AS propietario,
                    u.correo AS correo_propietario, (v.dispositivo_hash IS NOT NULL) AS tiene_clave_dispositivo,
                    (SELECT COUNT(*) FROM comandos c WHERE c.id_vehiculo = v.id_vehiculo AND c.activo = 1) AS comandos
               FROM vehiculos v
               JOIN modelos m ON m.id_modelo = v.id_modelo
          LEFT JOIN usuarios u ON u.id_usuario = v.id_propietario WHERE 1=1"""
    params = []
    if estado:
        sql += " AND v.estado_comercial = %s"
        params.append(estado.upper())
    if q:
        sql += " AND (v.numero_serie LIKE %s OR v.nombre LIKE %s OR u.nombre LIKE %s)"
        params += [f"%{q}%"] * 3
    filas = consultar(sql + " ORDER BY v.id_vehiculo", tuple(params))
    for f in filas:
        f["conectado"] = manager.dispositivo_conectado(f["id_vehiculo"])   # solo si es verificable
        f["en_uso"] = control_exclusivo.ocupado_por(f["id_vehiculo"]) is not None
    return filas


@router.post("/unidades", status_code=201, summary="Alta de unidad física (copia comandos de otra unidad del modelo)")
def crear_unidad(datos: UnidadCreate, p: Principal = Depends(requiere_admin)):
    estado = datos.estado_comercial.upper()
    if estado not in ("DISPONIBLE", "EXHIBICION"):
        raise HTTPException(422, "Una unidad nueva solo puede ser DISPONIBLE o EXHIBICION")
    modelo = consultar("SELECT * FROM modelos WHERE id_modelo = %s AND activo = 1", (datos.id_modelo,), uno=True)
    if not modelo:
        raise HTTPException(404, "Modelo no encontrado")
    plantilla = datos.copiar_comandos_de or (consultar(
        "SELECT id_vehiculo FROM vehiculos WHERE id_modelo = %s ORDER BY id_vehiculo LIMIT 1",
        (datos.id_modelo,), uno=True) or {}).get("id_vehiculo")
    if plantilla:
        pv = consultar("SELECT id_modelo FROM vehiculos WHERE id_vehiculo = %s", (plantilla,), uno=True)
        if not pv or pv["id_modelo"] != datos.id_modelo:
            raise HTTPException(422, "Los comandos solo se copian de una unidad del mismo modelo")
    try:
        with transaccion() as conn:
            cur = conn.cursor()
            cur.execute(
                """INSERT INTO vehiculos (nombre, modelo, id_modelo, numero_serie, estado_comercial, descripcion,
                                          microcontrolador)
                   VALUES (%s, %s, %s, %s, %s, %s, %s)""",
                (datos.nombre or modelo["nombre"], modelo["nombre"], datos.id_modelo, datos.numero_serie.strip().upper(),
                 estado, datos.descripcion or modelo["descripcion"], modelo["microcontrolador"]))
            nuevo = cur.lastrowid
            if plantilla:
                cur.execute(
                    """INSERT INTO comandos (id_vehiculo, nombre, codigo, descripcion, activo, permitido_invitado)
                       SELECT %s, nombre, codigo, descripcion, activo, permitido_invitado
                         FROM comandos WHERE id_vehiculo = %s""", (nuevo, plantilla))
            cur.close()
    except mysql.connector.Error as e:
        _duplicado(e, "Ya existe una unidad con ese número de serie")
    auditar(p, "CREAR_UNIDAD", "vehiculo", nuevo, "EXITO", f"{datos.numero_serie} ({modelo['nombre']})")
    return {"mensaje": "Unidad registrada", "id_vehiculo": nuevo, "comandos_copiados_de": plantilla}


@router.patch("/unidades/{id_vehiculo}", summary="Editar unidad o cambiar estado comercial (baja lógica = INACTIVO)")
async def editar_unidad(id_vehiculo: int, datos: UnidadUpdate, p: Principal = Depends(requiere_admin)):
    v = consultar("SELECT * FROM vehiculos WHERE id_vehiculo = %s", (id_vehiculo,), uno=True)
    if not v:
        raise HTTPException(404, "Unidad no encontrada")
    estado = (datos.estado_comercial or v["estado_comercial"]).upper()
    if datos.estado_comercial and estado not in ESTADOS_EDITABLES:
        raise HTTPException(422, "Estado no válido. VENDIDO se asigna con /asignar")
    if v["estado_comercial"] == "VENDIDO" and datos.estado_comercial and estado != "VENDIDO":
        raise HTTPException(409, "La unidad está vendida: primero retira la asignación con /desasignar")
    try:
        ejecutar("""UPDATE vehiculos SET numero_serie=%s, nombre=%s, descripcion=%s, estado_comercial=%s, activo=%s
                     WHERE id_vehiculo=%s""",
                 ((datos.numero_serie or v["numero_serie"]).upper(), datos.nombre or v["nombre"],
                  datos.descripcion if datos.descripcion is not None else v["descripcion"], estado,
                  0 if estado == "INACTIVO" else 1, id_vehiculo))
    except mysql.connector.Error as e:
        _duplicado(e, "Ya existe una unidad con ese número de serie")
    if estado != v["estado_comercial"]:
        # Si deja de ser de exhibición, se cierran las reservas de invitados
        if v["estado_comercial"] == "EXHIBICION":
            from app.routers.invitado import cerrar_reservas_de_unidad
            await cerrar_reservas_de_unidad(id_vehiculo, "UNIDAD_RETIRADA")
    auditar(p, "EDITAR_UNIDAD", "vehiculo", id_vehiculo, "EXITO", f"estado {v['estado_comercial']} -> {estado}")
    return {"mensaje": "Unidad actualizada"}


@router.post("/unidades/{id_vehiculo}/asignar", summary="Vender/asignar la unidad a un comprador")
async def asignar(id_vehiculo: int, datos: AsignacionRequest, p: Principal = Depends(requiere_admin)):
    cliente = consultar("""SELECT u.id_usuario, u.correo FROM usuarios u JOIN roles r ON r.id_rol = u.id_rol
                            WHERE u.id_usuario = %s AND u.activo = 1 AND r.nombre = 'USUARIO'""",
                        (datos.id_usuario,), uno=True)
    if not cliente:
        raise HTTPException(404, "Cliente comprador no encontrado o inactivo")
    with transaccion() as conn:
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT * FROM vehiculos WHERE id_vehiculo = %s FOR UPDATE", (id_vehiculo,))
        v = cur.fetchone()
        if not v or v["estado_comercial"] == "INACTIVO":
            raise HTTPException(404, "Unidad no encontrada o inactiva")
        if v["id_propietario"] == datos.id_usuario:
            raise HTTPException(409, "La unidad ya pertenece a ese cliente")
        anterior = v["id_propietario"]
        cur.execute("UPDATE asignaciones SET fecha_fin = UTC_TIMESTAMP() WHERE id_vehiculo = %s AND fecha_fin IS NULL",
                    (id_vehiculo,))
        cur.execute("""INSERT INTO asignaciones (id_vehiculo, id_usuario, id_admin, motivo)
                       VALUES (%s, %s, %s, %s)""", (id_vehiculo, datos.id_usuario, p.id_usuario, datos.motivo))
        cur.execute("""UPDATE vehiculos SET id_propietario = %s, estado_comercial = 'VENDIDO', soporte_hasta = NULL
                        WHERE id_vehiculo = %s""", (datos.id_usuario, id_vehiculo))
        cur.close()
    # Revocación inmediata: nadie más que el nuevo dueño queda suscrito al canal
    control_exclusivo.liberar(id_vehiculo)
    await manager.revocar(id_vehiculo, lambda c: c.tipo != "DISPOSITIVO" and c.id_usuario != datos.id_usuario,
                          "La unidad cambió de propietario")
    if v["estado_comercial"] == "EXHIBICION":
        from app.routers.invitado import cerrar_reservas_de_unidad
        await cerrar_reservas_de_unidad(id_vehiculo, "UNIDAD_VENDIDA")
    auditar(p, "ASIGNAR_UNIDAD", "vehiculo", id_vehiculo, "EXITO",
            f"de {anterior or 'empresa'} a {datos.id_usuario} ({cliente['correo']})")
    return {"mensaje": "Unidad asignada", "id_vehiculo": id_vehiculo, "id_usuario": datos.id_usuario}


@router.post("/unidades/{id_vehiculo}/desasignar", summary="Retirar la unidad al comprador (vuelve a la empresa)")
async def desasignar(id_vehiculo: int, datos: DesasignacionRequest, p: Principal = Depends(requiere_admin)):
    estado = datos.nuevo_estado.upper()
    if estado not in ESTADOS_EDITABLES:
        raise HTTPException(422, "Estado no válido")
    with transaccion() as conn:
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT * FROM vehiculos WHERE id_vehiculo = %s FOR UPDATE", (id_vehiculo,))
        v = cur.fetchone()
        if not v or not v["id_propietario"]:
            raise HTTPException(409, "La unidad no está asignada")
        cur.execute("UPDATE asignaciones SET fecha_fin = UTC_TIMESTAMP(), motivo = COALESCE(%s, motivo) "
                    "WHERE id_vehiculo = %s AND fecha_fin IS NULL", (datos.motivo, id_vehiculo))
        cur.execute("""UPDATE vehiculos SET id_propietario = NULL, estado_comercial = %s, soporte_hasta = NULL,
                              activo = %s WHERE id_vehiculo = %s""", (estado, 0 if estado == "INACTIVO" else 1, id_vehiculo))
        cur.close()
    control_exclusivo.liberar(id_vehiculo)
    await manager.revocar(id_vehiculo, lambda c: c.tipo != "DISPOSITIVO", "Asignación retirada")
    auditar(p, "DESASIGNAR_UNIDAD", "vehiculo", id_vehiculo, "EXITO", f"ex-propietario {v['id_propietario']} -> {estado}")
    return {"mensaje": "Asignación retirada"}


@router.get("/asignaciones", summary="Historial de asignaciones")
def listar_asignaciones(id_vehiculo: Optional[int] = None, p: Principal = Depends(requiere_admin)):
    sql = """SELECT a.*, v.numero_serie, u.nombre AS cliente, u.correo, ad.nombre AS administrador
               FROM asignaciones a
               JOIN vehiculos v ON v.id_vehiculo = a.id_vehiculo
               JOIN usuarios u ON u.id_usuario = a.id_usuario
          LEFT JOIN usuarios ad ON ad.id_usuario = a.id_admin"""
    if id_vehiculo:
        return consultar(sql + " WHERE a.id_vehiculo = %s ORDER BY a.id_asignacion DESC", (id_vehiculo,))
    return consultar(sql + " ORDER BY a.id_asignacion DESC LIMIT 100")


@router.post("/unidades/{id_vehiculo}/clave-dispositivo", summary="Generar clave del ESP8266 (se muestra una sola vez)")
async def clave_dispositivo(id_vehiculo: int, p: Principal = Depends(requiere_admin)):
    if not consultar("SELECT 1 AS x FROM vehiculos WHERE id_vehiculo = %s", (id_vehiculo,), uno=True):
        raise HTTPException(404, "Unidad no encontrada")
    clave = secrets.token_urlsafe(24)
    ejecutar("UPDATE vehiculos SET dispositivo_hash = %s WHERE id_vehiculo = %s", (sha256(clave), id_vehiculo))
    # La clave anterior deja de servir: se desconecta el dispositivo
    await manager.revocar(id_vehiculo, lambda c: c.tipo == "DISPOSITIVO", "Clave de dispositivo renovada")
    auditar(p, "CLAVE_DISPOSITIVO", "vehiculo", id_vehiculo, "EXITO", "Clave generada (no se guarda en texto)")
    return {"id_vehiculo": id_vehiculo, "clave_dispositivo": clave,
            "aviso": "Cópiala al firmware ahora; no se vuelve a mostrar."}


# ----------------------------------------------------------------- Auditoría y sesiones
@router.get("/auditoria", summary="Bitácora de auditoría (más reciente primero)")
def auditoria(limite: int = Query(50, ge=1, le=500), accion: Optional[str] = None,
              resultado: Optional[str] = None, p: Principal = Depends(requiere_admin)):
    sql, params = "SELECT * FROM auditoria WHERE 1=1", []
    if accion:
        sql += " AND accion = %s"
        params.append(accion.upper())
    if resultado:
        sql += " AND resultado = %s"
        params.append(resultado.upper())
    params.append(limite)
    return consultar(sql + " ORDER BY id_auditoria DESC LIMIT %s", tuple(params))


@router.get("/sesiones-invitado", summary="Sesiones de invitado activas")
def sesiones_invitado(p: Principal = Depends(requiere_admin)):
    return consultar("""SELECT s.id_sesion, s.alias, s.id_vehiculo, v.numero_serie, s.creada, s.expira
                          FROM sesiones s JOIN vehiculos v ON v.id_vehiculo = s.id_vehiculo
                         WHERE s.tipo = 'INVITADO' AND s.cerrada IS NULL AND s.expira > UTC_TIMESTAMP()
                         ORDER BY s.creada DESC""")
