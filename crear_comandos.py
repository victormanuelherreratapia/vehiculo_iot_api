from app.repositories import db_manager

COMANDOS = [
    ("SONIDO", "10", "Activar o quitar el sonido"),
    ("LED", "11", "Encender o apagar el LED"),
    ("DEMO_CONTROL", "12", "Activar la demo integrada del control"),
]

conn = db_manager.get_connection()
cur = conn.cursor()

# Consulta los parametros reales del procedimiento en RDS
cur.execute(
    "SELECT PARAMETER_NAME FROM information_schema.PARAMETERS "
    "WHERE SPECIFIC_SCHEMA = DATABASE() AND SPECIFIC_NAME = 'sp_crear_comando' "
    "ORDER BY ORDINAL_POSITION"
)
params = [fila[0] for fila in cur.fetchall()]
print("Parametros de sp_crear_comando:", params)

for nombre, codigo, desc in COMANDOS:
    valores = []
    for p in params:
        p_l = p.lower()
        if "vehiculo" in p_l:
            valores.append(1)
        elif "nombre" in p_l:
            valores.append(nombre)
        elif "codigo" in p_l:
            valores.append(codigo)
        elif "desc" in p_l:
            valores.append(desc)
        elif "activo" in p_l:
            valores.append(1)
        else:
            raise SystemExit("Parametro no reconocido: " + p)
    cur.callproc("sp_crear_comando", valores)
    for r in cur.stored_results():
        r.fetchall()
    print("OK:", nombre, "codigo", codigo)

conn.commit()
cur.close()
conn.close()
print("Listo: 3 comandos creados.")
