# API IoT Vehículo (FastAPI + POO) — Examen 2.6

API pública en AWS EC2 (HTTPS/WSS con Caddy + DuckDNS) conectada a Amazon RDS MySQL `vehiculo_iot`.

- Base URL: `https://vehiculoiot-victor.duckdns.org/api/v1`
- Swagger: `https://vehiculoiot-victor.duckdns.org/docs`
- WebSocket: `wss://vehiculoiot-victor.duckdns.org/ws/vehiculo/{id_vehiculo}`
- Seguridad: los POST requieren el header `X-API-Key`; los GET son públicos.

## Endpoints ↔ Stored Procedures

| Método | Endpoint | Stored Procedure |
|---|---|---|
| POST | /vehiculos | sp_insertar_vehiculo |
| GET | /vehiculos | sp_listar_vehiculos |
| GET | /vehiculos/{id} | sp_obtener_vehiculo |
| POST | /vehiculos/{id}/actualizar | sp_actualizar_vehiculo |
| POST | /vehiculos/{id}/eliminar | sp_eliminar_vehiculo |
| POST | /comandos | sp_insertar_comando |
| GET | /vehiculos/{id}/comandos | sp_listar_comandos |
| POST | /comandos/{id}/actualizar | sp_actualizar_comando |
| POST | /comandos/{id}/eliminar | sp_eliminar_comando |
| POST | /movimientos/individual | sp_actualizar_estado + sp_registrar_historial |
| GET | /vehiculos/{id}/estado | sp_obtener_estado |
| GET | /vehiculos/{id}/historial | sp_listar_historial (máx. 10) |
| POST | /demos | sp_insertar_demo |
| GET | /vehiculos/{id}/demos | sp_listar_demos |
| POST | /demos/{id}/actualizar | sp_actualizar_demo |
| POST | /demos/{id}/eliminar | sp_eliminar_demo |
| POST | /demos/movimientos | sp_insertar_demo_movimiento |
| GET | /demos/{id}/movimientos | sp_listar_demo_movimientos |
| POST | /demos/movimientos/{id}/actualizar | sp_actualizar_demo_movimiento |
| POST | /demos/movimientos/{id}/eliminar | sp_eliminar_demo_movimiento |
| POST | /vehiculos/{id}/demos/{id_demo}/iniciar | ejecuta la DEMO por WebSocket |

## Eventos WebSocket

```json
{"evento":"CONEXION_ESTABLECIDA","id_vehiculo":1}
{"evento":"MOVIMIENTO_INDIVIDUAL","id_vehiculo":1,"id_comando":1,"comando":"AVANZAR","codigo_comando":1,"timestamp":"..."}
{"evento":"DEMO_INICIO","id_vehiculo":1,"id_demo":1,"total_movimientos":8,"timestamp":"..."}
{"evento":"DEMO_MOVIMIENTO","id_vehiculo":1,"orden":1,"id_comando":1,"comando":"AVANZAR","codigo_comando":1,"duracion_ms":1000,"pausa_ms":300,"timestamp":"..."}
{"evento":"DEMO_FIN","id_vehiculo":1,"id_demo":1,"movimientos_ejecutados":8,"timestamp":"..."}
```

También existen `DEMO_CANCELADA` y `DEMO_ERROR`.

- Movimiento individual: actualiza el estado y guarda historial (transacción).
- DEMO: solo actualiza el estado, no guarda historial. Responde 409 si ya hay una DEMO en ejecución.
- Cancelar DEMO: `POST /vehiculos/{id}/demos/cancelar`.

## Ejecución local

```bash
pip install -r requirements.txt
cp .env.example .env
uvicorn main:app --host 127.0.0.1 --port 8000
```

Las credenciales (`.env`) no se suben al repositorio.

