from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class Segmento(BaseModel):
    inicio: float = Field(ge=0, allow_inf_nan=False)
    fin: float = Field(ge=0, allow_inf_nan=False)
    texto: str = Field(min_length=1, max_length=100000)

    @model_validator(mode="after")
    def check_times(self):
        if self.fin < self.inicio:
            raise ValueError("El final de un segmento debe ser posterior al inicio.")
        return self


class ResultadoTranscripcion(BaseModel):
    texto: str = Field(min_length=1, max_length=250000)
    idioma: str = Field(min_length=1, max_length=30)
    duracion_segundos: float = Field(gt=0, le=2700, allow_inf_nan=False)
    segmentos: list[Segmento] = Field(max_length=10000)
    modelo: str = Field(min_length=1, max_length=200)
    revision_manual: bool = False
    reunion_origen: str | None = Field(default=None, max_length=80)

    @field_validator("texto")
    @classmethod
    def nonempty_text(cls, value):
        if not value.strip():
            raise ValueError("La transcripción está vacía.")
        return value.strip()


class CrearReunion(BaseModel):
    request_id: str = Field(min_length=1, max_length=80, pattern=r"^[a-zA-Z0-9-]+$")
    title: str = Field(default="Reunión sin título", max_length=120)
    userName: str = Field(min_length=1, max_length=80)
    fileName: str = Field(min_length=1, max_length=255)
    transcription: ResultadoTranscripcion

    @field_validator("userName", "fileName")
    @classmethod
    def not_blank(cls, value):
        if not value.strip():
            raise ValueError("Este campo no puede estar vacío.")
        return value.strip()


class Resumen(BaseModel):
    model_config = ConfigDict(extra="forbid")
    temas: list[str] = Field(max_length=12)
    acuerdos: list[str] = Field(max_length=12)
    conclusiones: list[str] = Field(max_length=12)


class PropuestaPendiente(BaseModel):
    model_config = ConfigDict(extra="forbid")
    descripcion: str = Field(min_length=1, max_length=800)
    responsable: str = Field(min_length=1, max_length=80)
    fecha_limite: str | None = Field(max_length=150)
    evidencia: str = Field(min_length=1, max_length=2000)


class AnalisisModelo(BaseModel):
    model_config = ConfigDict(extra="forbid")
    resumen: Resumen
    pendientes: list[PropuestaPendiente] = Field(max_length=30)


class PuntoResumen(BaseModel):
    model_config = ConfigDict(extra="forbid")
    texto: str = Field(min_length=1, max_length=200)
    evidencia: str = Field(min_length=1, max_length=350)


class ResumenConEvidencia(BaseModel):
    model_config = ConfigDict(extra="forbid")
    temas: list[PuntoResumen] = Field(max_length=3)
    acuerdos: list[PuntoResumen] = Field(max_length=3)
    conclusiones: list[PuntoResumen] = Field(max_length=1)


class PropuestaDudosa(BaseModel):
    model_config = ConfigDict(extra="forbid")
    descripcion: str = Field(min_length=1, max_length=800)
    responsable: str | None = Field(max_length=80)
    fecha_limite: str | None = Field(max_length=150)
    evidencia: str = Field(min_length=1, max_length=2000)
    motivo: str = Field(min_length=1, max_length=300)


class ResolverPropuesta(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: int = Field(ge=0)
    decision: Literal["confirmar", "descartar"]
    responsable: str | None = Field(default=None, min_length=1, max_length=80)


class AnalisisConEvidencia(BaseModel):
    model_config = ConfigDict(extra="forbid")
    resumen: ResumenConEvidencia
    pendientes: list[PropuestaPendiente] = Field(max_length=30)
    por_confirmar: list[PropuestaDudosa] = Field(default_factory=list, max_length=15)
    sintesis: PuntoResumen | None = None


class EditarPendiente(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: int = Field(ge=0)
    nota: str | None = Field(default=None, max_length=10000)
    estado: Literal["pendiente", "en_curso", "completado"] | None = None

    @model_validator(mode="after")
    def changed_field(self):
        if self.nota is None and self.estado is None:
            raise ValueError("Indica una nota o un estado para guardar.")
        return self
