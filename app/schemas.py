"""Esquemas Pydantic de entrada/salida y esquemas estructurados para Gemini Vision."""

from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field


# =====================================================================
# Esquemas estructurados para extracción multimodal IA (response_schema)
# =====================================================================

class ExtraccionIcfesSchema(BaseModel):
    """Estructura extraída desde un soporte en PDF o imagen del Examen Saber 11°."""

    registro_snp: str = Field(..., description="Número de registro SNP del Examen Saber 11° (ej. AC20241001)")
    documento_identidad: str = Field(..., description="Número de documento de identidad del evaluado")
    nombres_completos: str = Field(..., description="Nombres y apellidos del aspirante")
    anio_examen: int = Field(..., description="Año de presentación del examen Saber 11°")
    fecha_presentacion: str = Field(..., description="Fecha de presentación en formato YYYY-MM-DD o texto")
    puntaje_global: float = Field(..., description="Puntaje global sobre 500")
    ciencias_naturales: float = Field(..., description="Puntaje en Ciencias Naturales")
    sociales_ciudadanas: float = Field(..., description="Puntaje en Sociales y Ciudadanas")
    matematicas: float = Field(..., description="Puntaje en Matemáticas")
    lectura_critica: float = Field(..., description="Puntaje en Lectura Crítica")
    ingles: float = Field(..., description="Puntaje en Inglés")
    es_valido: bool = Field(..., description="Indica si el reporte es auténtico y legible")
    observaciones: str = Field(..., description="Observaciones de auditoría documental IA")


class ExtraccionDiplomaSchema(BaseModel):
    """Estructura extraída desde un diploma/acta de bachiller o certificado de grado 11°."""

    documento_identidad: str = Field(..., description="Documento de identidad del estudiante o graduado")
    nombres_completos: str = Field(..., description="Nombres y apellidos del titular")
    institucion_educativa: str = Field(..., description="Nombre del colegio o institución educativa")
    tipo_soporte_educativo: str = Field(
        ...,
        description="DIPLOMA_BACHILLER, ACTA_GRADO o CERTIFICADO_GRADO_11",
    )
    anio_grado_o_curso: int = Field(..., description="Año de graduación o de curso de undécimo grado")
    es_valido: bool = Field(
        ...,
        description="True si acredita ser bachiller o estar cursando grado 11° al inscribirse",
    )
    observaciones: str = Field(..., description="Observaciones sobre la validez del soporte educativo")


class ExtraccionElectoralSchema(BaseModel):
    """Estructura extraída desde un certificado electoral para desempate."""

    documento_identidad: str = Field(..., description="Cédula de ciudadanía del sufragante")
    nombres_completos: str = Field(..., description="Nombres y apellidos del ciudadano")
    fecha_elecciones: str = Field(..., description="Fecha o jornada electoral del certificado")
    corresponde_ultimas_elecciones: bool = Field(
        ...,
        description="True si corresponde a las elecciones inmediatamente anteriores a la inscripción",
    )
    es_valido: bool = Field(
        ...,
        description="True si el certificado electoral es válido para el desempate reglamentario",
    )
    observaciones: str = Field(..., description="Observaciones sobre el certificado electoral")


# =====================================================================
# Esquemas de API REST (FastAPI)
# =====================================================================

class ProgramaAcademicoBase(BaseModel):
    codigo: str
    nombre: str
    facultad: str
    modalidad: str = "PRESENCIAL"
    cupos_ofertados: int = 5
    peso_ciencias_naturales: float
    peso_sociales_ciudadanas: float
    peso_matematicas: float
    peso_lectura_critica: float
    peso_ingles: float


class ProgramaAcademicoCreate(ProgramaAcademicoBase):
    pass


class ProgramaAcademicoOut(ProgramaAcademicoBase):
    id: int
    model_config = ConfigDict(from_attributes=True)


class SoporteDocumentalOut(BaseModel):
    id: int
    aspirante_id: int
    tipo_documento: str
    nombre_archivo: str
    ruta_archivo: str
    mime_type: str
    datos_extraidos_json: Optional[str] = None
    es_valido: bool
    observaciones_ia: Optional[str] = None
    fecha_carga: datetime
    model_config = ConfigDict(from_attributes=True)


class AspiranteCreate(BaseModel):
    orden_inscripcion: int
    tipo_documento: str = "CC"
    documento_identidad: str
    nombres: str
    apellidos: str
    correo: str
    edad: int = 18
    grupo_sisben: str = "OTROS"
    opciones_programas_ids: List[int] = Field(
        ..., description="Lista de IDs de programas (máximo 2 opciones)"
    )
    registro_snp: str
    anio_examen: int
    puntaje_global_declarado: float
    ciencias_naturales_declarado: float
    sociales_ciudadanas_declarado: float
    matematicas_declarado: float
    lectura_critica_declarado: float
    ingles_declarado: float
    nivel_educativo_valido: bool = True
    certificado_electoral_valido: bool = False


class AspiranteOut(BaseModel):
    id: int
    orden_inscripcion: int
    tipo_documento: str
    documento_identidad: str
    nombres: str
    apellidos: str
    correo: str
    edad: int
    grupo_sisben: str
    programa_opcion_1_id: int
    programa_opcion_2_id: Optional[int] = None
    programa_admitido_id: Optional[int] = None
    opcion_admitida: Optional[int] = None
    tarifa_inscripcion_smlmv: float
    registro_snp: str
    anio_examen: int
    puntaje_global_declarado: float
    ciencias_naturales_declarado: float
    sociales_ciudadanas_declarado: float
    matematicas_declarado: float
    lectura_critica_declarado: float
    ingles_declarado: float
    puntaje_global: Optional[float] = None
    ciencias_naturales: Optional[float] = None
    sociales_ciudadanas: Optional[float] = None
    matematicas: Optional[float] = None
    lectura_critica: Optional[float] = None
    ingles: Optional[float] = None
    nivel_educativo_valido: bool
    certificado_electoral_valido: bool
    puntaje_ponderado_op1: Optional[float] = None
    puntaje_ponderado_op2: Optional[float] = None
    estado_proceso: str
    causal_decision: Optional[str] = None
    notificacion_inconsistencia: Optional[str] = None
    codigo_estudiante_uis: Optional[str] = None
    hoja_vida_academica: Optional[str] = None
    carta_admision: Optional[str] = None
    log_auditoria: str
    soportes: List[SoporteDocumentalOut] = []
    model_config = ConfigDict(from_attributes=True)


class CopilotChatRequest(BaseModel):
    mensaje: str
    historial: Optional[List[Dict[str, str]]] = None


class CopilotChatResponse(BaseModel):
    respuesta: str
    herramientas_invocadas: List[str] = []
    modo_ia: str = "deterministic_fallback"
    uso_llm: bool = False
    latencia_ms: int = 0
    datos_contexto: Optional[Dict[str, Any]] = None


class GeminiConfigRequest(BaseModel):
    api_key: Optional[str] = None
    modelo: Optional[str] = None
    persistir_env: bool = True
