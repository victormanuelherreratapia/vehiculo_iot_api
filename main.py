from fastapi import FastAPI
from app.routers import vehiculos, websockets

app = FastAPI(
    title="API Vehículo IoT - Entorno Dev",
    description="API REST con FastAPI, POO, RDS MySQL y WebSockets para el control de vehículos IoT.",
    version="1.0.0"
)

app.include_router(vehiculos.router)
app.include_router(websockets.router)

@app.get("/", tags=["Root"])
def root():
    return {"mensaje": "Servidor de API IoT ejecutándose correctamente en localhost:8000"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)