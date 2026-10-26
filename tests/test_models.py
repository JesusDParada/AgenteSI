"""Pruebas unitarias para la base de datos SQLite, modelos SQLAlchemy y esquemas Pydantic."""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import (
    Aspirante,
    MockHistoricoUis,
    MockIcfesOficial,
    ProgramaAcademico,
    SoporteDocumental,
)
from app.schemas import AspiranteOut, ExtraccionIcfesSchema, ProgramaAcademicoOut


def test_creacion_tablas_y_persistencia_cinco_entidades():
    """Verifica que las 5 entidades SQLite se creen y persistan correctamente."""
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    TestingSession = sessionmaker(bind=engine)
    db = TestingSession()

    try:
        # 1. ProgramaAcademico
        prog = ProgramaAcademico(
            codigo="ING-SIS",
            nombre="Ingeniería de Sistemas",
            facultad="Facultad de Ingenierías Físico-Mecánicas",
            cupos_ofertados=3,
            peso_ciencias_naturales=25.0,
            peso_sociales_ciudadanas=10.0,
            peso_matematicas=40.0,
            peso_lectura_critica=15.0,
            peso_ingles=10.0,
        )
        db.add(prog)
        db.commit()
        db.refresh(prog)

        # 2. Aspirante
        asp = Aspirante(
            orden_inscripcion=1,
            documento_identidad="1098765432",
            nombres="Camila Andrea",
            apellidos="Gómez Ruiz",
            correo="camila.gomez@correo.uis.edu.co",
            edad=19,
            grupo_sisben="B",
            programa_opcion_1_id=prog.id,
            tarifa_inscripcion_smlmv=0.05,
            registro_snp="AC20241001",
            anio_examen=2024,
            puntaje_global_declarado=385.0,
            ciencias_naturales_declarado=76.0,
            sociales_ciudadanas_declarado=72.0,
            matematicas_declarado=84.0,
            lectura_critica_declarado=78.0,
            ingles_declarado=75.0,
        )
        asp.append_log("INSCRIPCION", "Registro inicial de prueba")
        db.add(asp)
        db.commit()
        db.refresh(asp)

        # 3. SoporteDocumental
        sop = SoporteDocumental(
            aspirante_id=asp.id,
            tipo_documento="ICFES",
            nombre_archivo="icfes_1098765432.pdf",
            ruta_archivo="seed_docs/icfes_1098765432.pdf",
            mime_type="application/pdf",
            es_valido=True,
            observaciones_ia="Soporte válido",
        )
        db.add(sop)

        # 4. MockIcfesOficial
        icfes = MockIcfesOficial(
            registro_snp="AC20241001",
            documento_identidad="1098765432",
            nombres_completos="Camila Andrea Gómez Ruiz",
            anio_examen=2024,
            fecha_presentacion="2024-08-18",
            puntaje_global=385.0,
            ciencias_naturales=76.0,
            sociales_ciudadanas=72.0,
            matematicas=84.0,
            lectura_critica=78.0,
            ingles=75.0,
        )
        db.add(icfes)

        # 5. MockHistoricoUis
        hist = MockHistoricoUis(
            documento_identidad="1099999999",
            nombres_completos="Carlos Pérez",
            tipo_inhabilidad="PFU",
            vigente=True,
            descripcion_causal="Pérdida de calidad de estudiante por bajo rendimiento (P.F.U.)",
            periodo_registro="2025-2",
        )
        db.add(hist)
        db.commit()

        # Verificar consultas y esquemas Pydantic
        prog_schema = ProgramaAcademicoOut.model_validate(prog)
        assert prog_schema.codigo == "ING-SIS"

        db.refresh(asp)
        asp_schema = AspiranteOut.model_validate(asp)
        assert asp_schema.documento_identidad == "1098765432"
        assert len(asp_schema.soportes) == 1
        assert asp_schema.soportes[0].tipo_documento == "ICFES"

        extraccion = ExtraccionIcfesSchema(
            registro_snp="AC20241001",
            documento_identidad="1098765432",
            nombres_completos="Camila Andrea Gómez Ruiz",
            anio_examen=2024,
            fecha_presentacion="2024-08-18",
            puntaje_global=385.0,
            ciencias_naturales=76.0,
            sociales_ciudadanas=72.0,
            matematicas=84.0,
            lectura_critica=78.0,
            ingles=75.0,
            es_valido=True,
            observaciones="OK",
        )
        assert extraccion.puntaje_global == 385.0
    finally:
        db.close()
