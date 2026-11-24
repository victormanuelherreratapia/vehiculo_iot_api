import asyncio

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.database import consultar
from app.routers import admin, auth, control_demo, cuenta, invitado, vehiculos, websockets

app = FastAPI(
    title="API Vehículo IoT - Plataforma comercial",
    description=(
        "API REST + WebSocket para CONTROL, MONITOREO y ADMINISTRACIÓN de vehículos IoT "
        "(FastAPI, POO, Amazon RDS MySQL).\n\n"
        "**Roles:** ADMIN (empresa), USUARIO (comprador) e INVITADO (prueba temporal).\n\n"
        "1. `POST /api/v1/auth/login` (o `POST /api/v1/invitado/sesiones`) devuelve un token.\n"
        "2. Botón **Authorize** → pega el token en *BearerAuth*.\n\n"
        "Cada ruta comprueba el rol **y** el permiso sobre la unidad concreta (propiedad, reserva o soporte)."
    ),
    version="4.3.0",
)

# Orígenes autorizados (CORS solo indica qué páginas pueden llamar a la API
# desde el navegador; NO es autenticación ni protege el WebSocket).
ORIGENES_PERMITIDOS = [
    "https://victormanuelherreratapia.github.io",  # GitHub Pages
    "http://127.0.0.1:5500",                        # Live Server (pruebas locales)
    "http://localhost:5500",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ORIGENES_PERMITIDOS,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-API-Key"],
    allow_credentials=False,
    max_age=600,
)

app.include_router(auth.router)
app.include_router(invitado.router)
app.include_router(cuenta.router)
app.include_router(admin.router)
app.include_router(vehiculos.router)
app.include_router(control_demo.router)
app.include_router(websockets.router)


@app.on_event("startup")
async def iniciar_tareas():
    # Cierra pruebas de invitado vencidas o sin conexión y detiene la unidad
    app.state.vigilante = asyncio.create_task(invitado.vigilante_invitados())


@app.get("/", tags=["Root"])
def root():
    return {"mensaje": "Servidor de API IoT ejecutándose correctamente"}


@app.get("/api/v1/salud", tags=["Root"], summary="Salud de la API y diagnóstico de RDS (desde el backend)")
async def salud():
    try:
        await asyncio.to_thread(consultar, "SELECT 1 AS ok", (), True)
        return {"api": "disponible", "rds": "disponible"}
    except Exception:
        return JSONResponse(status_code=503, content={"api": "disponible", "rds": "no disponible"})


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
