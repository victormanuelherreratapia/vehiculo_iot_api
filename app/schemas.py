from pydantic import BaseModel
from typing import Optional

class VehiculoCreate(BaseModel):
    nombre: str
    modelo: str
    activo: bool = True

class VehiculoUpdate(BaseModel):
    nombre: Optional[str] = None
    modelo: Optional[str] = None
    activo: Optional[bool] = None

class ComandoCreate(BaseModel):
    id_vehiculo: int
    nombre_comando: str
    codigo_comando: str
    descripcion: Optional[str] = None
    activo: bool = True

class ComandoUpdate(BaseModel):
    nombre_comando: Optional[str] = None
    codigo_comando: Optional[str] = None
    descripcion: Optional[str] = None
    activo: Optional[bool] = None

class MovimientoIndividualRequest(BaseModel):
    id_vehiculo: int
    id_comando: int
    origen: str = "ThunderClient_Dev"

class DemoCreate(BaseModel):
    id_vehiculo: int
    nombre_demo: str
    descripcion: Optional[str] = None
    activa: bool = True

class DemoUpdate(BaseModel):
    nombre_demo: Optional[str] = None
    descripcion: Optional[str] = None
    activa: Optional[bool] = None

class MovimientoDemoCreate(BaseModel):
    id_demo: int
    id_comando: int
    orden: int
    duracion_ms: int
    pausa_ms: int

class MovimientoDemoUpdate(BaseModel):
    orden: Optional[int] = None
    duracion_ms: Optional[int] = None
    pausa_ms: Optional[int] = None