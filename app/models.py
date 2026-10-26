"""Modelos ORM de SQLAlchemy para el procedimiento PAR.01 de la DARA - UIS."""

from datetime import datetime, timezone
import json
from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from app.database import Base


class ProgramaAcademico(Base):
    """Entidad de Programa Académico de Pregrado UIS con sus ponderaciones Saber 11°."""

    __tablename__ = "programas_academicos"

    id = Column(Integer, primary_key=True, index=True)
    codigo = Column(String(30), unique=True, index=True, nullable=False)
    nombre = Column(String(150), nullable=False)
    facultad = Column(String(120), nullable=False)
    modalidad = Column(String(40), default="PRESENCIAL", nullable=False)
    cupos_ofertados = Column(Integer, nullable=False, default=5)

    # Pesos porcentuales por área Saber 11° (suman 100%)
    peso_ciencias_naturales = Column(Float, nullable=False)
    peso_sociales_ciudadanas = Column(Float, nullable=False)
    peso_matematicas = Column(Float, nullable=False)
    peso_lectura_critica = Column(Float, nullable=False)
    peso_ingles = Column(Float, nullable=False)


class Aspirante(Base):
    """Entidad de Aspirante inscrito en el proceso de admisión PAR.01."""

    __tablename__ = "aspirantes"

    id = Column(Integer, primary_key=True, index=True)
    orden_inscripcion = Column(Integer, unique=True, index=True, nullable=False)
    tipo_documento = Column(String(15), default="CC", nullable=False)
    documento_identidad = Column(String(30), unique=True, index=True, nullable=False)
    nombres = Column(String(100), nullable=False)
    apellidos = Column(String(100), nullable=False)
    correo = Column(String(120), nullable=False)
    edad = Column(Integer, default=18, nullable=False)
    grupo_sisben = Column(String(20), default="OTROS", nullable=False)

    programa_opcion_1_id = Column(
        Integer, ForeignKey("programas_academicos.id"), nullable=False
    )
    programa_opcion_2_id = Column(
        Integer, ForeignKey("programas_academicos.id"), nullable=True
    )
    programa_admitido_id = Column(
        Integer, ForeignKey("programas_academicos.id"), nullable=True
    )
    opcion_admitida = Column(Integer, nullable=True)

    tarifa_inscripcion_smlmv = Column(Float, default=0.0, nullable=False)

    # Datos ICFES declarados al momento de la inscripción
    registro_snp = Column(String(40), index=True, nullable=False)
    anio_examen = Column(Integer, nullable=False)
    puntaje_global_declarado = Column(Float, nullable=False)
    ciencias_naturales_declarado = Column(Float, nullable=False)
    sociales_ciudadanas_declarado = Column(Float, nullable=False)
    matematicas_declarado = Column(Float, nullable=False)
    lectura_critica_declarado = Column(Float, nullable=False)
    ingles_declarado = Column(Float, nullable=False)

    # Datos ICFES verificados tras cruce con fuente oficial (Paso 4)
    puntaje_global = Column(Float, nullable=True)
    ciencias_naturales = Column(Float, nullable=True)
    sociales_ciudadanas = Column(Float, nullable=True)
    matematicas = Column(Float, nullable=True)
    lectura_critica = Column(Float, nullable=True)
    ingles = Column(Float, nullable=True)

    # Validaciones de soportes (nivel educativo y certificado electoral)
    nivel_educativo_valido = Column(Boolean, default=True, nullable=False)
    certificado_electoral_valido = Column(Boolean, default=False, nullable=False)

    # Puntajes ponderados y resultados del motor de selección (Pasos 5-12)
    puntaje_ponderado_op1 = Column(Float, nullable=True)
    puntaje_ponderado_op2 = Column(Float, nullable=True)
    estado_proceso = Column(String(50), default="INSCRITO", nullable=False)
    causal_decision = Column(Text, nullable=True)
    notificacion_inconsistencia = Column(Text, nullable=True)

    # Datos de admisión final (Paso 12)
    codigo_estudiante_uis = Column(String(30), nullable=True)
    hoja_vida_academica = Column(Text, nullable=True)
    carta_admision = Column(Text, nullable=True)
    log_auditoria = Column(Text, default="[]", nullable=False)

    programa_opcion_1 = relationship(
        "ProgramaAcademico", foreign_keys=[programa_opcion_1_id]
    )
    programa_opcion_2 = relationship(
        "ProgramaAcademico", foreign_keys=[programa_opcion_2_id]
    )
    programa_admitido = relationship(
        "ProgramaAcademico", foreign_keys=[programa_admitido_id]
    )
    soportes = relationship(
        "SoporteDocumental",
        back_populates="aspirante",
        cascade="all, delete-orphan",
    )

    def append_log(self, etapa: str, detalle: str) -> None:
        """Agrega una entrada de trazabilidad en el campo JSON log_auditoria."""
        try:
            actual = json.loads(self.log_auditoria or "[]")
        except Exception:
            actual = []
        actual.append(
            {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "etapa": etapa,
                "detalle": detalle,
            }
        )
        self.log_auditoria = json.dumps(actual, ensure_ascii=False)


class SoporteDocumental(Base):
    """Metadatos y resultado de extracción IA de un archivo PDF o imagen de soporte."""

    __tablename__ = "soportes_documentales"

    id = Column(Integer, primary_key=True, index=True)
    aspirante_id = Column(
        Integer, ForeignKey("aspirantes.id", ondelete="CASCADE"), nullable=False
    )
    tipo_documento = Column(String(40), nullable=False)  # ICFES | DIPLOMA_BACHILLER | CERTIFICADO_ELECTORAL
    nombre_archivo = Column(String(255), nullable=False)
    ruta_archivo = Column(String(500), nullable=False)
    mime_type = Column(String(80), nullable=False)
    datos_extraidos_json = Column(Text, nullable=True)
    es_valido = Column(Boolean, default=False, nullable=False)
    observaciones_ia = Column(Text, nullable=True)
    fecha_carga = Column(
        DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )

    aspirante = relationship("Aspirante", back_populates="soportes")


class MockIcfesOficial(Base):
    """Base de datos nacional simulada del ICFES para cruce masivo del Paso 4."""

    __tablename__ = "mock_icfes_oficial"

    id = Column(Integer, primary_key=True, index=True)
    registro_snp = Column(String(40), unique=True, index=True, nullable=False)
    documento_identidad = Column(String(30), index=True, nullable=False)
    nombres_completos = Column(String(200), nullable=False)
    anio_examen = Column(Integer, nullable=False)
    fecha_presentacion = Column(String(30), nullable=False)
    puntaje_global = Column(Float, nullable=False)
    ciencias_naturales = Column(Float, nullable=False)
    sociales_ciudadanas = Column(Float, nullable=False)
    matematicas = Column(Float, nullable=False)
    lectura_critica = Column(Float, nullable=False)
    ingles = Column(Float, nullable=False)


class MockHistoricoUis(Base):
    """Archivo histórico simulado de hojas de vida UIS para cruce del Paso 7 (P.F.U. y sanciones)."""

    __tablename__ = "mock_historico_uis"

    id = Column(Integer, primary_key=True, index=True)
    documento_identidad = Column(String(30), unique=True, index=True, nullable=False)
    nombres_completos = Column(String(200), nullable=False)
    tipo_inhabilidad = Column(
        String(50), nullable=False
    )  # PFU | SANCION_DISCIPLINARIA | FALTA_RENOVACION
    vigente = Column(Boolean, default=True, nullable=False)
    descripcion_causal = Column(Text, nullable=False)
    periodo_registro = Column(String(20), nullable=False)
