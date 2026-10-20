import hmac

from fastapi import FastAPI, Request
from fastapi.openapi.utils import get_openapi
from fastapi.responses import JSONResponse

from app.config import settings
from app.routers import vehiculos, websockets

app = FastAPI(
    title="API Vehículo IoT - Entorno Dev",
    description="API REST con FastAPI, POO, RDS MySQL y WebSockets para el control de vehículos IoT.",
    version="1.0.0"
)

METODOS_SEGUROS = {"GET", "HEAD", "OPTIONS"}


@app.middleware("http")
async def proteger_operaciones(request: Request, call_next):
    """Exige la cabecera X-API-Key en toda operación que modifica datos (POST)."""
    if request.method not in METODOS_SEGUROS:
        clave = request.headers.get("x-api-key", "")
        esperada = settings.API_KEY
        if not esperada or not hmac.compare_digest(clave.encode(), esperada.encode()):
            return JSONResponse(
                status_code=401,
                content={"detail": "API key inválida o ausente"},
            )
    return await call_next(request)


app.include_router(vehiculos.router)
app.include_router(websockets.router)


def custom_openapi():
    """Muestra el botón Authorize en Swagger UI para los POST."""
    if app.openapi_schema:
        return app.openapi_schema
    schema = get_openapi(
        title=app.title,
        version=app.version,
        description=app.description,
        routes=app.routes,
    )
    schema.setdefault("components", {}).setdefault("securitySchemes", {})["ApiKeyAuth"] = {
        "type": "apiKey",
        "in": "header",
        "name": "X-API-Key",
    }
    for path, metodos in schema["paths"].items():
        for metodo, operacion in metodos.items():
            if metodo.lower() == "post":
                operacion["security"] = [{"ApiKeyAuth": []}]
    app.openapi_schema = schema
    return schema


app.openapi = custom_openapi


@app.get("/", tags=["Root"])
def root():
    return {"mensaje": "Servidor de API IoT ejecutándose correctamente"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)