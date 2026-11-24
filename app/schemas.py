from typing import List, Optional

from pydantic import BaseModel, Field


# ====================== Esquemas originales (21 APIs) ======================
class VehiculoCreate(BaseModel):
    nombre: str = Field(..., min_length=2, max_length=80)
    modelo: str = Field(..., max_length=80)
    descripcion: Optional[str] = Field(None, max_length=255)
    microcontrolador: Optional[str] = Field(None, max_length=50)
    activo: bool = True


class VehiculoUpdate(BaseModel):
    nombre: Optional[str] = Field(None, max_length=80)
    modelo: Optional[str] = Field(None, max_length=80)
    descripcion: Optional[str] = Field(None, max_length=255)
    microcontrolador: Optional[str] = Field(None, max_length=50)
    activo: Optional[bool] = None


class ComandoCreate(BaseModel):
    id_vehiculo: int
    nombre_comando: str = Field(..., max_length=60)
    codigo_comando: int = Field(..., ge=0, le=255)
    descripcion: Optional[str] = Field(None, max_length=255)
    activo: bool = True


class ComandoUpdate(BaseModel):
    nombre_comando: Optional[str] = Field(None, max_length=60)
    codigo_comando: Optional[int] = Field(None, ge=0, le=255)
    descripcion: Optional[str] = Field(None, max_length=255)
    activo: Optional[bool] = None


class MovimientoIndividualRequest(BaseModel):
    id_vehiculo: int
    id_comando: int
    # Se conserva por compatibilidad; el servidor guarda el origen según la sesión.
    origen: str = "WebControl"


class DemoCreate(BaseModel):
    id_vehiculo: int
    nombre_demo: str = Field(..., max_length=80)
    descripcion: Optional[str] = Field(None, max_length=255)
    activa: bool = True


class DemoUpdate(BaseModel):
    nombre_demo: Optional[str] = Field(None, max_length=80)
    descripcion: Optional[str] = Field(None, max_length=255)
    activa: Optional[bool] = None


class MovimientoDemoCreate(BaseModel):
    id_demo: int
    id_comando: int
    orden: int = Field(..., ge=1)
    duracion_ms: int = Field(..., ge=1)
    pausa_ms: int = Field(0, ge=0)


class MovimientoDemoUpdate(BaseModel):
    id_comando: Optional[int] = None
    orden: Optional[int] = Field(None, ge=1)
    duracion_ms: Optional[int] = Field(None, ge=1)
    pausa_ms: Optional[int] = Field(None, ge=0)


# ====================== Práctica 4.3 ======================
class LoginRequest(BaseModel):
    correo: str = Field(..., min_length=5, max_length=120, examples=["admin@ejemplo.com"])
    password: str = Field(..., min_length=1, max_length=128)


class UsuarioCreate(BaseModel):
    nombre: str = Field(..., min_length=3, max_length=100)
    correo: str = Field(..., min_length=5, max_length=120)
    telefono: Optional[str] = Field(None, max_length=20)
    password: str = Field(..., min_length=10, max_length=128)
    rol: str = Field("USUARIO", description="USUARIO (comprador) o ADMIN")


class UsuarioUpdate(BaseModel):
    nombre: Optional[str] = Field(None, min_length=3, max_length=100)
    telefono: Optional[str] = Field(None, max_length=20)
    activo: Optional[bool] = None
    password: Optional[str] = Field(None, min_length=10, max_length=128)


class ModeloCreate(BaseModel):
    nombre: str = Field(..., min_length=2, max_length=80)
    descripcion: Optional[str] = Field(None, max_length=255)
    microcontrolador: Optional[str] = Field(None, max_length=50)
    imagen: Optional[str] = Field(None, max_length=255)
    publicado: bool = True


class ModeloUpdate(BaseModel):
    nombre: Optional[str] = Field(None, min_length=2, max_length=80)
    descripcion: Optional[str] = Field(None, max_length=255)
    microcontrolador: Optional[str] = Field(None, max_length=50)
    imagen: Optional[str] = Field(None, max_length=255)
    publicado: Optional[bool] = None
    activo: Optional[bool] = None


class UnidadCreate(BaseModel):
    id_modelo: int
    numero_serie: str = Field(..., min_length=3, max_length=40)
    nombre: Optional[str] = Field(None, max_length=80, description="Si se omite, se usa el nombre del modelo")
    descripcion: Optional[str] = Field(None, max_length=255)
    estado_comercial: str = Field("DISPONIBLE", description="DISPONIBLE o EXHIBICION")
    copiar_comandos_de: Optional[int] = Field(None, description="Unidad de la que se copian los comandos (mismo modelo)")


class UnidadUpdate(BaseModel):
    numero_serie: Optional[str] = Field(None, min_length=3, max_length=40)
    nombre: Optional[str] = Field(None, max_length=80)
    descripcion: Optional[str] = Field(None, max_length=255)
    estado_comercial: Optional[str] = Field(None, description="DISPONIBLE, EXHIBICION o INACTIVO (VENDIDO solo por asignación)")


class AsignacionRequest(BaseModel):
    id_usuario: int
    motivo: Optional[str] = Field(None, max_length=150)


class DesasignacionRequest(BaseModel):
    motivo: Optional[str] = Field(None, max_length=150)
    nuevo_estado: str = Field("DISPONIBLE", description="DISPONIBLE, EXHIBICION o INACTIVO")


class SoporteRequest(BaseModel):
    minutos: int = Field(30, ge=5, le=240)


class PasoDemo(BaseModel):
    id_comando: int
    duracion_ms: int = Field(..., ge=1)
    pausa_ms: int = Field(0, ge=0)


class DemoEditor(BaseModel):
    id_vehiculo: int
    nombre: str = Field(..., min_length=3, max_length=80)
    descripcion: Optional[str] = Field(None, max_length=255)
    pasos: List[PasoDemo]


class SesionInvitadoRequest(BaseModel):
    id_vehiculo: int
    alias: Optional[str] = Field(None, max_length=60)
