"""
Herramienta de migraciones versionadas para vehiculo_iot (práctica 4.3).

Usa las MISMAS credenciales de la API (archivo .env del servidor); no
contiene contraseñas. Se ejecuta desde C:\\vehiculo_iot_api:

  python migraciones\\migrar.py copia                  Crea vehiculo_iot_prueba desde el último respaldo
  python migraciones\\migrar.py conteo    <base>       Cuenta filas de cada tabla
  python migraciones\\migrar.py aplicar   <base>       Aplica las migraciones pendientes (V001...)
  python migraciones\\migrar.py verificar <base>       Pruebas de integridad después de migrar
  python migraciones\\migrar.py revertir  <base>       Ejecuta V001 DOWN (solo para la copia de prueba)
  python migraciones\\migrar.py admin     <base>       Crea la cuenta de Administrador (pide la contraseña)

En MySQL cada CREATE/ALTER hace COMMIT implícito: si un paso falla a la
mitad, NO hay rollback automático. Por eso se prueba primero en la copia.
"""
import datetime
import getpass
import glob
import hashlib
import os
import re
import secrets
import sys

import mysql.connector

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)
from app.config import settings  # noqa: E402

CARPETA = os.path.dirname(os.path.abspath(__file__))
RESPALDOS = r"C:\respaldos"
BASE_REAL = settings.DB_NAME
BASE_PRUEBA = "vehiculo_iot_prueba"
TABLAS_ORIGINALES = ["vehiculos", "comandos", "estado_vehiculo", "historial_comandos", "demos", "demo_movimientos"]


def conectar(base=None):
    conn = mysql.connector.connect(
        host=settings.DB_HOST, user=settings.DB_USER, password=settings.DB_PASSWORD,
        port=settings.DB_PORT, database=base, autocommit=False,
    )
    cur = conn.cursor()
    cur.execute("SET time_zone = '+00:00'")
    cur.close()
    return conn


def sentencias(texto):
    """Divide un script SQL en sentencias (soporta bloques DELIMITER $$ del respaldo)."""
    delimitador, actual = ";", []
    for linea in texto.splitlines():
        limpia = linea.strip()
        if limpia.upper().startswith("DELIMITER "):
            delimitador = limpia.split()[1]
            continue
        if not actual and (not limpia or limpia.startswith("--")):
            continue
        actual.append(linea)
        if limpia.endswith(delimitador):
            sql = "\n".join(actual).rstrip()[: -len(delimitador)].strip()
            actual = []
            if sql:
                yield sql
    resto = "\n".join(actual).strip()
    if resto:
        yield resto


def conteo(base, imprimir=True):
    conn = conectar(base)
    cur = conn.cursor()
    cur.execute("SHOW FULL TABLES WHERE Table_type = 'BASE TABLE'")
    datos = {}
    for (tabla, _tipo) in cur.fetchall():
        cur.execute(f"SELECT COUNT(*) FROM `{tabla}`")
        datos[tabla] = cur.fetchone()[0]
    cur.close(); conn.close()
    if imprimir:
        print(f"\nConteo en {base}:")
        for t, n in sorted(datos.items()):
            print(f"  {t:<22} {n:>6}")
    return datos


def copia():
    archivos = sorted(glob.glob(os.path.join(RESPALDOS, "respaldo_vehiculo_iot_*.sql")))
    if not archivos:
        sys.exit(f"No hay respaldos en {RESPALDOS}")
    respaldo = archivos[-1]
    print("Respaldo:", respaldo)
    conn = conectar()
    cur = conn.cursor()
    cur.execute(f"DROP DATABASE IF EXISTS `{BASE_PRUEBA}`")
    cur.execute(f"CREATE DATABASE `{BASE_PRUEBA}` CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci")
    cur.execute(f"USE `{BASE_PRUEBA}`")
    texto = open(respaldo, encoding="utf-8").read()
    n = 0
    for sql in sentencias(texto):
        sql = re.sub(r"DEFINER=`[^`]+`@`[^`]+`\s*", "", sql)   # el procedimiento queda a nombre del usuario actual
        cur.execute(sql)
        n += 1
    conn.commit()
    cur.close(); conn.close()
    print(f"Copia {BASE_PRUEBA} creada ({n} sentencias).")
    original, prueba = conteo(BASE_REAL, False), conteo(BASE_PRUEBA, False)
    print("\nComparación original vs copia:")
    for t in TABLAS_ORIGINALES:
        marca = "OK" if original.get(t) == prueba.get(t) else "DIFERENTE"
        print(f"  {t:<22} {original.get(t):>6} {prueba.get(t):>6}  {marca}")


def asegurar_control(cur):
    cur.execute("""
        CREATE TABLE IF NOT EXISTS schema_migraciones (
          version     VARCHAR(10)  NOT NULL PRIMARY KEY,
          descripcion VARCHAR(120) NOT NULL,
          checksum    CHAR(64)     NOT NULL,
          aplicada_en TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
          resultado   VARCHAR(20)  NOT NULL
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""")


def confirmar_real(base, accion):
    if base == BASE_REAL:
        print(f"\n*** ATENCIÓN: vas a {accion} la base REAL '{base}'. ***")
        print("Confirma que ya probaste en la copia y que existe el snapshot respaldo-antes-4-3.")
        if input(f"Escribe el nombre de la base para continuar: ").strip() != base:
            sys.exit("Cancelado.")


def aplicar(base):
    confirmar_real(base, "migrar")
    antes = conteo(base, False)
    conn = conectar(base)
    cur = conn.cursor()
    asegurar_control(cur)
    cur.execute("SELECT version FROM schema_migraciones WHERE resultado = 'APLICADA'")
    hechas = {v for (v,) in cur.fetchall()}
    pendientes = sorted(f for f in glob.glob(os.path.join(CARPETA, "V*__*.sql")) if not f.endswith("_DOWN.sql"))
    for ruta in pendientes:
        nombre = os.path.basename(ruta)
        version, desc = nombre.split("__", 1)
        if version in hechas:
            print(f"{version} ya aplicada, se omite.")
            continue
        texto = open(ruta, encoding="utf-8").read()
        checksum = hashlib.sha256(texto.encode()).hexdigest()
        print(f"\nAplicando {nombre} en {base} ...")
        for i, sql in enumerate(sentencias(texto), 1):
            primera = sql.splitlines()[0][:70]
            try:
                cur.execute(sql)
                conn.commit()
                print(f"  [{i:02}] OK  {primera}")
            except mysql.connector.Error as e:
                conn.rollback()
                print(f"  [{i:02}] ERROR {primera}\n        {e}")
                cur.execute("REPLACE INTO schema_migraciones (version, descripcion, checksum, resultado) VALUES (%s,%s,%s,'FALLIDA')",
                            (version, desc[:-4][:120], checksum))
                conn.commit()
                sys.exit("\nSe detuvo la migración. Revisa el error antes de continuar (no hay rollback automático de DDL).")
        cur.execute("REPLACE INTO schema_migraciones (version, descripcion, checksum, resultado) VALUES (%s,%s,%s,'APLICADA')",
                    (version, desc[:-4][:120], checksum))
        conn.commit()
        print(f"{version} aplicada.")
    cur.close(); conn.close()
    despues = conteo(base, False)
    print("\nFilas de las tablas originales (antes -> después):")
    for t in TABLAS_ORIGINALES:
        marca = "OK" if antes.get(t) == despues.get(t) else "CAMBIÓ"
        print(f"  {t:<22} {antes.get(t):>6} -> {despues.get(t):>6}  {marca}")


def verificar(base):
    conn = conectar(base)
    cur = conn.cursor(dictionary=True)
    pruebas = [
        ("Migración V001 registrada", "SELECT COUNT(*) n FROM schema_migraciones WHERE version='V001' AND resultado='APLICADA'", lambda n: n == 1),
        ("Roles ADMIN y USUARIO", "SELECT COUNT(*) n FROM roles", lambda n: n == 2),
        ("Toda unidad tiene modelo", "SELECT COUNT(*) n FROM vehiculos WHERE id_modelo IS NULL", lambda n: n == 0),
        ("Número de serie único", "SELECT COUNT(*) - COUNT(DISTINCT numero_serie) n FROM vehiculos", lambda n: n == 0),
        ("Historial sin huérfanos", "SELECT COUNT(*) n FROM historial_comandos h LEFT JOIN vehiculos v ON v.id_vehiculo=h.id_vehiculo WHERE v.id_vehiculo IS NULL", lambda n: n == 0),
        ("Pasos de demo con comando válido", "SELECT COUNT(*) n FROM demo_movimientos d LEFT JOIN comandos c ON c.id_comando=d.id_comando WHERE c.id_comando IS NULL", lambda n: n == 0),
        ("Comandos para invitado", "SELECT COUNT(*) n FROM comandos WHERE permitido_invitado=1", lambda n: n > 0),
        ("DETENER permitido al invitado", "SELECT COUNT(*) n FROM comandos WHERE codigo=9 AND permitido_invitado=1", lambda n: n >= 1),
        ("Demos existentes = FABRICA", "SELECT COUNT(*) n FROM demos WHERE tipo<>'FABRICA'", lambda n: n == 0),
        ("Índice del historial", "SELECT COUNT(*) n FROM information_schema.STATISTICS WHERE TABLE_SCHEMA=DATABASE() AND INDEX_NAME='idx_historial_vehiculo_fecha'", lambda n: n >= 1),
        ("Historial protegido (RESTRICT)", "SELECT COUNT(*) n FROM information_schema.REFERENTIAL_CONSTRAINTS WHERE CONSTRAINT_SCHEMA=DATABASE() AND CONSTRAINT_NAME='fk_historial_vehiculo' AND DELETE_RULE='RESTRICT'", lambda n: n == 1),
    ]
    fallas = 0
    print(f"\nVerificación de {base}:")
    for nombre, sql, ok in pruebas:
        try:
            cur.execute(sql)
            n = cur.fetchone()["n"]
            bien = ok(n)
        except mysql.connector.Error as e:
            n, bien = str(e)[:60], False
        fallas += not bien
        print(f"  {'OK   ' if bien else 'FALLA'} {nombre} ({n})")

    # Los procedimientos que usan CONTROL y MONITOREO deben seguir funcionando
    for sp, args in [("sp_obtener_vehiculo", (1,)), ("sp_obtener_estado", (1,)), ("sp_obtener_historial", (1,)),
                     ("sp_obtener_comandos_vehiculo", (1,)), ("sp_obtener_demos", (1,))]:
        try:
            cur.callproc(sp, args)
            filas = [r.fetchall() for r in cur.stored_results()][0]
            print(f"  OK    {sp}{args} -> {len(filas)} filas")
        except mysql.connector.Error as e:
            fallas += 1
            print(f"  FALLA {sp}: {e}")
    cur.execute("SELECT id_vehiculo, nombre, id_modelo, numero_serie, estado_comercial, id_propietario FROM vehiculos")
    print("\nUnidades:")
    for v in cur.fetchall():
        print("  ", v)
    cur.close(); conn.close()
    print("\nRESULTADO:", "TODO CORRECTO" if fallas == 0 else f"{fallas} FALLA(S)")


def revertir(base):
    if base == BASE_REAL:
        sys.exit("La reversión automática solo se permite en la copia. En la base real se restaura el snapshot.")
    conn = conectar(base)
    cur = conn.cursor()
    texto = open(os.path.join(CARPETA, "V001__plataforma_comercial_DOWN.sql"), encoding="utf-8").read()
    for sql in sentencias(texto):
        cur.execute(sql)
        conn.commit()
        print("  OK ", sql.splitlines()[0][:70])
    cur.execute("DELETE FROM schema_migraciones WHERE version='V001'")
    conn.commit()
    cur.close(); conn.close()
    conteo(base)


def hash_password(clave: str) -> str:
    sal = secrets.token_hex(16)
    iteraciones = 390000
    dk = hashlib.pbkdf2_hmac("sha256", clave.encode(), bytes.fromhex(sal), iteraciones).hex()
    return f"pbkdf2_sha256${iteraciones}${sal}${dk}"


def crear_admin(base):
    nombre = input("Nombre del administrador: ").strip()
    correo = input("Correo (será el usuario de inicio de sesión): ").strip().lower()
    clave = getpass.getpass("Contraseña (mín. 10 caracteres, no se muestra): ")
    if len(clave) < 10 or clave != getpass.getpass("Repite la contraseña: "):
        sys.exit("La contraseña no coincide o es muy corta.")
    conn = conectar(base)
    cur = conn.cursor()
    cur.execute("INSERT INTO usuarios (id_rol, nombre, correo, password_hash) VALUES (1, %s, %s, %s)",
                (nombre, correo, hash_password(clave)))
    cur.execute("INSERT INTO auditoria (id_usuario, actor, rol, accion, recurso, id_recurso, resultado, detalle) "
                "VALUES (%s, %s, 'SISTEMA', 'CREAR_ADMIN', 'usuario', %s, 'EXITO', 'Cuenta inicial creada desde migrar.py')",
                (cur.lastrowid, correo, str(cur.lastrowid)))
    conn.commit()
    cur.close(); conn.close()
    print(f"Administrador {correo} creado en {base}.")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    orden = sys.argv[1]
    base = sys.argv[2] if len(sys.argv) > 2 else BASE_PRUEBA
    if orden == "copia":
        copia()
    elif orden == "conteo":
        conteo(base)
    elif orden == "aplicar":
        aplicar(base)
    elif orden == "verificar":
        verificar(base)
    elif orden == "revertir":
        revertir(base)
    elif orden == "admin":
        crear_admin(base)
    else:
        sys.exit(__doc__)
