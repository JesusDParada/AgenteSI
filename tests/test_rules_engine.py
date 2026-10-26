"""Pruebas unitarias para el motor determinista de reglas PAR.01 (app/services/rules_engine.py)."""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import Aspirante, ProgramaAcademico
from app.services.rules_engine import (
    ejecutar_paso5_validacion_puntajes_minimos,
    liquidar_derechos_inscripcion,
    validar_aspirante_paso5,
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


def test_liquidacion_tarifas_sisben_primera_y_segunda_opcion():
    """Verifica el cálculo exacto en SMLMV según el grupo SISBÉN y número de opciones."""
    # Escenario del spec: Grupo B con primera y segunda opción -> 0.050 + 0.0250 = 0.0750 SMLMV
    res_b = liquidar_derechos_inscripcion("Grupo B", num_opciones=2)
    assert res_b["categoria_sisben"] == "B"
    assert res_b["tarifa_opcion_1_smlmv"] == 0.050
    assert res_b["tarifa_opcion_2_smlmv"] == 0.0250
    assert res_b["total_smlmv"] == 0.0750

    # Grupo A con 1 opción
    res_a = liquidar_derechos_inscripcion("A2", num_opciones=1)
    assert res_a["categoria_sisben"] == "A"
    assert res_a["total_smlmv"] == 0.025

    # Grupo C1 a C10 con 2 opciones -> 0.075 + 0.0375 = 0.1125
    res_c = liquidar_derechos_inscripcion("C5", num_opciones=2)
    assert res_c["categoria_sisben"] == "C1-C10"
    assert res_c["total_smlmv"] == 0.1125

    # Otros casos (ej. C15 o OTROS) con 2 opciones -> 0.100 + 0.0500 = 0.1500
    res_otros = liquidar_derechos_inscripcion("C15", num_opciones=2)
    assert res_otros["categoria_sisben"] == "OTROS"
    assert res_otros["total_smlmv"] == 0.1500


def test_rechazo_mas_de_dos_opciones_programa():
    """Verifica que inscribir más de dos programas académicos sea rechazado por límite reglamentario."""
    with pytest.raises(ValueError, match="máximo 2 opciones"):
        liquidar_derechos_inscripcion("B", num_opciones=3)

    with pytest.raises(ValueError):
        liquidar_derechos_inscripcion("A", num_opciones=0)


def test_paso5_anulacion_por_puntaje_inferior_a_31_y_vigencia(db_session):
    """Verifica que el Paso 5 anule inscripciones con <31 en algún área o examen vencido (>5 años)."""
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

    # Caso 1: Aspirante con 29 puntos en Inglés (< 31)
    asp_bajo_puntaje = Aspirante(
        orden_inscripcion=1,
        documento_identidad="1001",
        nombres="Juan",
        apellidos="Baja Nota",
        correo="juan@test.com",
        programa_opcion_1_id=prog.id,
        registro_snp="AC20240001",
        anio_examen=2024,
        puntaje_global_declarado=340.0,
        ciencias_naturales_declarado=70.0,
        sociales_ciudadanas_declarado=68.0,
        matematicas_declarado=75.0,
        lectura_critica_declarado=72.0,
        ingles_declarado=29.0,
        estado_proceso="VERIFICADO_ICFES",
    )

    # Caso 2: Aspirante con examen vencido (2019 en convocatoria 2026 -> 7 años > 5 años)
    asp_vencido = Aspirante(
        orden_inscripcion=2,
        documento_identidad="1002",
        nombres="Ana",
        apellidos="Examen Vencido",
        correo="ana@test.com",
        programa_opcion_1_id=prog.id,
        registro_snp="AC20190002",
        anio_examen=2019,
        puntaje_global_declarado=390.0,
        ciencias_naturales_declarado=80.0,
        sociales_ciudadanas_declarado=78.0,
        matematicas_declarado=82.0,
        lectura_critica_declarado=75.0,
        ingles_declarado=74.0,
        estado_proceso="VERIFICADO_ICFES",
    )

    # Caso 3: Aspirante que cumple todo (>=31 en las 5 áreas y año 2023 en convocatoria 2026)
    asp_ok = Aspirante(
        orden_inscripcion=3,
        documento_identidad="1003",
        nombres="Laura",
        apellidos="Cumple Todo",
        correo="laura@test.com",
        programa_opcion_1_id=prog.id,
        registro_snp="AC20230003",
        anio_examen=2023,
        puntaje_global_declarado=400.0,
        ciencias_naturales_declarado=80.0,
        sociales_ciudadanas_declarado=80.0,
        matematicas_declarado=85.0,
        lectura_critica_declarado=80.0,
        ingles_declarado=75.0,
        estado_proceso="VERIFICADO_ICFES",
    )

    db_session.add_all([asp_bajo_puntaje, asp_vencido, asp_ok])
    db_session.commit()

    res = ejecutar_paso5_validacion_puntajes_minimos(db_session, anio_convocatoria=2026)
    assert res["total_evaluados"] == 3
    assert res["habilitados"] == 1
    assert res["anulados_puntaje_minimo"] == 1
    assert res["anulados_vigencia_examen"] == 1

    db_session.refresh(asp_bajo_puntaje)
    db_session.refresh(asp_vencido)
    db_session.refresh(asp_ok)

    assert asp_bajo_puntaje.estado_proceso == "ANULADO_PUNTAJE_MINIMO"
    assert "Inglés (29.0 pts < 31)" in asp_bajo_puntaje.causal_decision

    assert asp_vencido.estado_proceso == "ANULADO_VIGENCIA_EXAMEN"
    assert "2019" in asp_vencido.causal_decision

    assert asp_ok.estado_proceso == "HABILITADO"

    # Validar también que año < 2012 se anule incluso si anio_convocatoria fuera cercano
    asp_2011 = Aspirante(
        orden_inscripcion=4,
        documento_identidad="1004",
        nombres="Pedro",
        apellidos="Pre 2012",
        correo="pedro@test.com",
        programa_opcion_1_id=prog.id,
        registro_snp="AC20110004",
        anio_examen=2011,
        puntaje_global_declarado=380.0,
        ciencias_naturales_declarado=75.0,
        sociales_ciudadanas_declarado=75.0,
        matematicas_declarado=75.0,
        lectura_critica_declarado=75.0,
        ingles_declarado=75.0,
    )
    res_2011 = validar_aspirante_paso5(asp_2011, anio_convocatoria=2015)
    assert not res_2011["habilitado"]
    assert res_2011["estado"] == "ANULADO_VIGENCIA_EXAMEN"
