"""Pruebas unitarias para el módulo de Auditoría Documental Multimodal IA y Paso 4 ICFES (app/services/ai_agent.py)."""

import pytest
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
from app.services.ai_agent import (
    auditar_soporte_multimodal,
    ejecutar_paso4_verificacion_icfes,
    generar_informe_y_acta_comite,
    procesar_mensaje_copiloto,
)


@pytest.fixture
def db_session():
    """Crea una sesión SQLite en memoria limpia para cada prueba."""
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    try:
        yield session
    finally:
        session.close()


def test_extraccion_multimodal_soportes_icfes_diploma_y_electoral(db_session, tmp_path, monkeypatch):
    """Verifica la extracción estructurada de soportes en PDF e imagen (ICFES, Diploma y Certificado Electoral)."""
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)

    prog = ProgramaAcademico(
        codigo="ING-SIS",
        nombre="Ingeniería de Sistemas",
        facultad="Facultad de Ingenierías Físico-Mecánicas",
        cupos_ofertados=2,
        peso_ciencias_naturales=25.0,
        peso_sociales_ciudadanas=10.0,
        peso_matematicas=40.0,
        peso_lectura_critica=15.0,
        peso_ingles=10.0,
    )
    db_session.add(prog)
    db_session.commit()

    db_session.add(
        MockIcfesOficial(
            registro_snp="AC20245001",
            documento_identidad="1095001",
            nombres_completos="Sofía Vergara Rojas",
            anio_examen=2024,
            fecha_presentacion="2024-08-18",
            puntaje_global=392.0,
            ciencias_naturales=78.0,
            sociales_ciudadanas=74.0,
            matematicas=86.0,
            lectura_critica=80.0,
            ingles=74.0,
        )
    )

    asp = Aspirante(
        orden_inscripcion=1,
        documento_identidad="1095001",
        nombres="Sofía",
        apellidos="Vergara Rojas",
        correo="sofia@test.com",
        edad=19,
        programa_opcion_1_id=prog.id,
        registro_snp="AC20245001",
        anio_examen=2024,
        puntaje_global_declarado=392.0,
        ciencias_naturales_declarado=78.0,
        sociales_ciudadanas_declarado=74.0,
        matematicas_declarado=86.0,
        lectura_critica_declarado=80.0,
        ingles_declarado=74.0,
        certificado_electoral_valido=False,
    )
    db_session.add(asp)
    db_session.commit()

    # Crear archivos simulados PDF y PNG en tmp_path
    pdf_icfes = tmp_path / "icfes_1095001.pdf"
    pdf_icfes.write_bytes(b"%PDF-1.4 mock icfes content")

    png_diploma = tmp_path / "diploma_1095001.png"
    png_diploma.write_bytes(b"\x89PNG\r\n\x1a\nmock diploma")

    png_electoral = tmp_path / "certificado_electoral_1095001.png"
    png_electoral.write_bytes(b"\x89PNG\r\n\x1a\nmock electoral")

    sop_icfes = SoporteDocumental(
        aspirante_id=asp.id,
        tipo_documento="ICFES",
        nombre_archivo=pdf_icfes.name,
        ruta_archivo=str(pdf_icfes),
        mime_type="application/pdf",
    )
    sop_diploma = SoporteDocumental(
        aspirante_id=asp.id,
        tipo_documento="DIPLOMA_BACHILLER",
        nombre_archivo=png_diploma.name,
        ruta_archivo=str(png_diploma),
        mime_type="image/png",
    )
    sop_electoral = SoporteDocumental(
        aspirante_id=asp.id,
        tipo_documento="CERTIFICADO_ELECTORAL",
        nombre_archivo=png_electoral.name,
        ruta_archivo=str(png_electoral),
        mime_type="image/png",
    )
    db_session.add_all([sop_icfes, sop_diploma, sop_electoral])
    db_session.commit()

    res_icfes = auditar_soporte_multimodal(db_session, sop_icfes.id)
    assert res_icfes["es_valido"] is True
    assert res_icfes["datos_extraidos"]["registro_snp"] == "AC20245001"
    assert res_icfes["datos_extraidos"]["matematicas"] == 86.0

    res_dip = auditar_soporte_multimodal(db_session, sop_diploma.id)
    assert res_dip["es_valido"] is True
    assert res_dip["datos_extraidos"]["tipo_soporte_educativo"] == "DIPLOMA_BACHILLER"

    res_elec = auditar_soporte_multimodal(db_session, sop_electoral.id)
    assert res_elec["es_valido"] is True
    assert res_elec["datos_extraidos"]["corresponde_ultimas_elecciones"] is True

    db_session.refresh(asp)
    assert asp.nivel_educativo_valido is True
    assert asp.certificado_electoral_valido is True


def test_paso4_cruce_icfes_coincidencia_e_inconsistencia(db_session):
    """Verifica el cruce masivo del Paso 4 contra MockIcfesOficial y la generación del correo de inconsistencia."""
    prog = ProgramaAcademico(
        codigo="ING-SIS",
        nombre="Ingeniería de Sistemas",
        facultad="Facultad de Ingenierías Físico-Mecánicas",
        cupos_ofertados=2,
        peso_ciencias_naturales=25.0,
        peso_sociales_ciudadanas=10.0,
        peso_matematicas=40.0,
        peso_lectura_critica=15.0,
        peso_ingles=10.0,
    )
    db_session.add(prog)
    db_session.commit()

    # Registro oficial en el ICFES
    db_session.add_all(
        [
            MockIcfesOficial(
                registro_snp="AC20246001",
                documento_identidad="6001",
                nombres_completos="Valeria Exacta",
                anio_examen=2024,
                fecha_presentacion="2024-08-18",
                puntaje_global=375.0,
                ciencias_naturales=75.0,
                sociales_ciudadanas=75.0,
                matematicas=75.0,
                lectura_critica=75.0,
                ingles=75.0,
            ),
            MockIcfesOficial(
                registro_snp="AC20246002",
                documento_identidad="6002",
                nombres_completos="Diego Inconsistente",
                anio_examen=2024,
                fecha_presentacion="2024-08-18",
                puntaje_global=330.0,
                ciencias_naturales=65.0,
                sociales_ciudadanas=66.0,
                matematicas=68.0,
                lectura_critica=67.0,
                ingles=64.0,
            ),
        ]
    )

    # Aspirante 1: Coincide exactamente con ICFES
    asp_ok = Aspirante(
        orden_inscripcion=1,
        documento_identidad="6001",
        nombres="Valeria",
        apellidos="Exacta",
        correo="valeria@test.com",
        programa_opcion_1_id=prog.id,
        registro_snp="AC20246001",
        anio_examen=2024,
        puntaje_global_declarado=375.0,
        ciencias_naturales_declarado=75.0,
        sociales_ciudadanas_declarado=75.0,
        matematicas_declarado=75.0,
        lectura_critica_declarado=75.0,
        ingles_declarado=75.0,
    )

    # Aspirante 2: Declaró Matemáticas=95.0 cuando en el ICFES tiene 68.0
    asp_inc = Aspirante(
        orden_inscripcion=2,
        documento_identidad="6002",
        nombres="Diego",
        apellidos="Inconsistente",
        correo="diego@test.com",
        programa_opcion_1_id=prog.id,
        registro_snp="AC20246002",
        anio_examen=2024,
        puntaje_global_declarado=410.0,
        ciencias_naturales_declarado=65.0,
        sociales_ciudadanas_declarado=66.0,
        matematicas_declarado=95.0,
        lectura_critica_declarado=67.0,
        ingles_declarado=64.0,
    )

    db_session.add_all([asp_ok, asp_inc])
    db_session.commit()

    res = ejecutar_paso4_verificacion_icfes(db_session)
    assert res["total_procesados"] == 2
    assert res["verificados_icfes"] == 1
    assert res["inconsistencias_detectadas"] == 1

    db_session.refresh(asp_ok)
    db_session.refresh(asp_inc)

    assert asp_ok.estado_proceso == "VERIFICADO_ICFES"
    assert asp_ok.matematicas == 75.0
    assert asp_ok.notificacion_inconsistencia is None

    assert asp_inc.estado_proceso == "INCONSISTENCIA_ICFES"
    assert asp_inc.notificacion_inconsistencia is not None
    assert "admisiones@uis.edu.co" in asp_inc.notificacion_inconsistencia
    assert "Matemáticas" in asp_inc.notificacion_inconsistencia


def test_copiloto_dara_tool_calling_ejecucion_consulta_y_acta(db_session, monkeypatch):
    """Verifica que el Agente Copiloto de la DARA invoque las herramientas de selección, consulta y acta con trazabilidad."""
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)

    prog = ProgramaAcademico(
        codigo="ING-SIS",
        nombre="Ingeniería de Sistemas",
        facultad="Facultad de Ingenierías Físico-Mecánicas",
        cupos_ofertados=1,
        peso_ciencias_naturales=25.0,
        peso_sociales_ciudadanas=10.0,
        peso_matematicas=40.0,
        peso_lectura_critica=15.0,
        peso_ingles=10.0,
    )
    db_session.add(prog)
    db_session.commit()

    db_session.add_all(
        [
            MockIcfesOficial(
                registro_snp="AC20247001",
                documento_identidad="7001",
                nombres_completos="Mateo PFU",
                anio_examen=2024,
                fecha_presentacion="2024-08-18",
                puntaje_global=420.0,
                ciencias_naturales=85.0,
                sociales_ciudadanas=80.0,
                matematicas=90.0,
                lectura_critica=82.0,
                ingles=80.0,
            ),
            MockIcfesOficial(
                registro_snp="AC20247002",
                documento_identidad="7002",
                nombres_completos="Lucía Admitida",
                anio_examen=2024,
                fecha_presentacion="2024-08-18",
                puntaje_global=395.0,
                ciencias_naturales=78.0,
                sociales_ciudadanas=76.0,
                matematicas=84.0,
                lectura_critica=79.0,
                ingles=75.0,
            ),
        ]
    )
    db_session.add(
        MockHistoricoUis(
            documento_identidad="7001",
            nombres_completos="Mateo PFU",
            tipo_inhabilidad="PFU",
            vigente=True,
            descripcion_causal="Pérdida de calidad de estudiante por bajo rendimiento académico (P.F.U.)",
            periodo_registro="2025-1",
        )
    )

    asp1 = Aspirante(
        orden_inscripcion=1,
        documento_identidad="7001",
        nombres="Mateo",
        apellidos="PFU",
        correo="mateo@test.com",
        programa_opcion_1_id=prog.id,
        registro_snp="AC20247001",
        anio_examen=2024,
        puntaje_global_declarado=420.0,
        ciencias_naturales_declarado=85.0,
        sociales_ciudadanas_declarado=80.0,
        matematicas_declarado=90.0,
        lectura_critica_declarado=82.0,
        ingles_declarado=80.0,
    )
    asp2 = Aspirante(
        orden_inscripcion=2,
        documento_identidad="7002",
        nombres="Lucía",
        apellidos="Admitida",
        correo="lucia@test.com",
        programa_opcion_1_id=prog.id,
        registro_snp="AC20247002",
        anio_examen=2024,
        puntaje_global_declarado=395.0,
        ciencias_naturales_declarado=78.0,
        sociales_ciudadanas_declarado=76.0,
        matematicas_declarado=84.0,
        lectura_critica_declarado=79.0,
        ingles_declarado=75.0,
    )
    db_session.add_all([asp1, asp2])
    db_session.commit()

    # 1. Pedir al copiloto ejecutar la selección completa
    r_exec = procesar_mensaje_copiloto(
        db_session, "Por favor ejecuta el flujo completo de selección y asignación de cupos"
    )
    assert "ejecutar_seleccion_completa_par01" in r_exec["herramientas_invocadas"]
    assert "Procedimiento PAR.01" in r_exec["respuesta"]

    # 2. Preguntar al copiloto por qué Mateo (7001) fue inhabilitado
    r_mateo = procesar_mensaje_copiloto(
        db_session, "¿Por qué fue inhabilitado Mateo con documento 7001?"
    )
    assert "consultar_aspirante" in r_mateo["herramientas_invocadas"]
    assert "INHABILITADO_HISTORICO_UIS" in r_mateo["respuesta"]
    assert "PFU" in r_mateo["respuesta"]

    # 3. Pedir al copiloto redactar el informe y borrador de acta para el Comité de Admisiones y Consejo Académico
    r_acta = procesar_mensaje_copiloto(
        db_session, "Genera el informe y borrador de acta para el Comité de Admisiones y Consejo Académico"
    )
    assert "generar_acta_comite_admisiones" in r_acta["herramientas_invocadas"]
    assert "CONSEJO ACADÉMICO" in r_acta["respuesta"]
    assert "Lucía Admitida" in r_acta["respuesta"]

    # Verificar también llamada directa a generar_informe_y_acta_comite
    acta_directa = generar_informe_y_acta_comite(db_session)
    assert acta_directa["resumen"]["total_admitidos"] == 1
    assert acta_directa["resumen"]["desglose_anuladas"]["INHABILITADO_HISTORICO_UIS"] == 1

