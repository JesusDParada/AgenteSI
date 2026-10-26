"""Pruebas unitarias para el motor determinista de reglas PAR.01 (app/services/rules_engine.py)."""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import Aspirante, MockHistoricoUis, ProgramaAcademico
from app.services.rules_engine import (
    calcular_promedio_ponderado,
    ejecutar_paso5_validacion_puntajes_minimos,
    ejecutar_paso12_hoja_vida_y_cartas_admision,
    ejecutar_pasos_6_y_7_seleccion_y_cruce_historico,
    generar_listados_oficiales,
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
    res_b = liquidar_derechos_inscripcion("Grupo B", num_opciones=2)
    assert res_b["categoria_sisben"] == "B"
    assert res_b["tarifa_opcion_1_smlmv"] == 0.050
    assert res_b["tarifa_opcion_2_smlmv"] == 0.0250
    assert res_b["total_smlmv"] == 0.0750

    res_a = liquidar_derechos_inscripcion("A2", num_opciones=1)
    assert res_a["categoria_sisben"] == "A"
    assert res_a["total_smlmv"] == 0.025

    res_c = liquidar_derechos_inscripcion("C5", num_opciones=2)
    assert res_c["categoria_sisben"] == "C1-C10"
    assert res_c["total_smlmv"] == 0.1125

    res_otros = liquidar_derechos_inscripcion("C15", num_opciones=2)
    assert res_otros["categoria_sisben"] == "OTROS"
    assert res_otros["total_smlmv"] == 0.1500


def test_rechazo_mas_de_dos_opciones_programa():
    """Verifica que inscribir más de dos programas académicos sea rechazado por límite reglamentario."""
    with pytest.raises(ValueError, match="máximo 2"):
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
    assert asp_ok.estado_proceso == "HABILITADO"

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


def test_cinco_reglas_desempate_en_cascada(db_session):
    """Verifica el orden estricto de las 5 reglas de desempate ante igual puntaje ponderado."""
    # Programa con pesos iguales (20% cada área) para que permutar CN/MAT/ING mantenga el mismo ponderado
    prog = ProgramaAcademico(
        codigo="TEST-EMP",
        nombre="Ingeniería Industrial",
        facultad="Facultad de Ingenierías Físico-Mecánicas",
        cupos_ofertados=5,
        peso_ciencias_naturales=20.0,
        peso_sociales_ciudadanas=20.0,
        peso_matematicas=20.0,
        peso_lectura_critica=20.0,
        peso_ingles=20.0,
    )
    db_session.add(prog)
    db_session.commit()

    # Todos los 6 aspirantes tendrán exactamente promedio ponderado = 70.0000 (suma de áreas = 350)
    # 1. Gana por Regla 1: Mayor Puntaje Global (395 vs 380 del resto)
    a_regla1 = Aspirante(
        orden_inscripcion=60,
        documento_identidad="2001",
        nombres="Ganador",
        apellidos="Regla1 Global",
        correo="r1@test.com",
        edad=19,
        programa_opcion_1_id=prog.id,
        registro_snp="AC20242001",
        anio_examen=2024,
        puntaje_global_declarado=395.0,
        ciencias_naturales_declarado=70.0,
        sociales_ciudadanas_declarado=70.0,
        matematicas_declarado=70.0,
        lectura_critica_declarado=70.0,
        ingles_declarado=70.0,
        estado_proceso="HABILITADO",
    )

    # 2. Gana por Regla 2: Mismo Global (380), pero mayor Lectura Crítica (75 vs 70 del resto; compensado con Inglés 65)
    a_regla2 = Aspirante(
        orden_inscripcion=50,
        documento_identidad="2002",
        nombres="Ganador",
        apellidos="Regla2 Lectura",
        correo="r2@test.com",
        edad=19,
        programa_opcion_1_id=prog.id,
        registro_snp="AC20242002",
        anio_examen=2024,
        puntaje_global_declarado=380.0,
        ciencias_naturales_declarado=70.0,
        sociales_ciudadanas_declarado=70.0,
        matematicas_declarado=70.0,
        lectura_critica_declarado=75.0,
        ingles_declarado=65.0,
        estado_proceso="HABILITADO",
    )

    # 3. Gana por Regla 3: Mismo Global (380), misma Lectura (70), pero mayor Sociales (74 vs 70; Inglés 66)
    a_regla3 = Aspirante(
        orden_inscripcion=40,
        documento_identidad="2003",
        nombres="Ganador",
        apellidos="Regla3 Sociales",
        correo="r3@test.com",
        edad=19,
        programa_opcion_1_id=prog.id,
        registro_snp="AC20242003",
        anio_examen=2024,
        puntaje_global_declarado=380.0,
        ciencias_naturales_declarado=70.0,
        sociales_ciudadanas_declarado=74.0,
        matematicas_declarado=70.0,
        lectura_critica_declarado=70.0,
        ingles_declarado=66.0,
        estado_proceso="HABILITADO",
    )

    # 4. Gana por Regla 4: Mismo Global (380), Lectura (70), Sociales (70), pero tiene Certificado Electoral Válido y edad=20
    a_regla4 = Aspirante(
        orden_inscripcion=30,
        documento_identidad="2004",
        nombres="Ganador",
        apellidos="Regla4 Voto",
        correo="r4@test.com",
        edad=20,
        certificado_electoral_valido=True,
        programa_opcion_1_id=prog.id,
        registro_snp="AC20242004",
        anio_examen=2024,
        puntaje_global_declarado=380.0,
        ciencias_naturales_declarado=70.0,
        sociales_ciudadanas_declarado=70.0,
        matematicas_declarado=70.0,
        lectura_critica_declarado=70.0,
        ingles_declarado=70.0,
        estado_proceso="HABILITADO",
    )

    # 5. Gana por Regla 5: Sin certificado electoral, pero menor orden_inscripcion (10 vs 20)
    a_regla5 = Aspirante(
        orden_inscripcion=10,
        documento_identidad="2005",
        nombres="Ganador",
        apellidos="Regla5 Orden10",
        correo="r5@test.com",
        edad=19,
        certificado_electoral_valido=False,
        programa_opcion_1_id=prog.id,
        registro_snp="AC20242005",
        anio_examen=2024,
        puntaje_global_declarado=380.0,
        ciencias_naturales_declarado=70.0,
        sociales_ciudadanas_declarado=70.0,
        matematicas_declarado=70.0,
        lectura_critica_declarado=70.0,
        ingles_declarado=70.0,
        estado_proceso="HABILITADO",
    )

    # 6. Pierde por Regla 5: Mismo todo que a_regla5, pero orden_inscripcion=20
    a_perdedor = Aspirante(
        orden_inscripcion=20,
        documento_identidad="2006",
        nombres="Perdedor",
        apellidos="Orden20",
        correo="r6@test.com",
        edad=19,
        certificado_electoral_valido=False,
        programa_opcion_1_id=prog.id,
        registro_snp="AC20242006",
        anio_examen=2024,
        puntaje_global_declarado=380.0,
        ciencias_naturales_declarado=70.0,
        sociales_ciudadanas_declarado=70.0,
        matematicas_declarado=70.0,
        lectura_critica_declarado=70.0,
        ingles_declarado=70.0,
        estado_proceso="HABILITADO",
    )

    db_session.add_all([a_perdedor, a_regla5, a_regla4, a_regla3, a_regla2, a_regla1])
    db_session.commit()

    res = ejecutar_pasos_6_y_7_seleccion_y_cruce_historico(db_session)
    assert res["admitidos_primera_opcion"] == 5
    assert res["no_admitidos"] == 1

    for a in [a_regla1, a_regla2, a_regla3, a_regla4, a_regla5, a_perdedor]:
        db_session.refresh(a)
        assert a.puntaje_ponderado_op1 == 70.0

    assert "Puesto 1/5" in a_regla1.causal_decision
    assert "Puesto 2/5" in a_regla2.causal_decision
    assert "Puesto 3/5" in a_regla3.causal_decision
    assert "Puesto 4/5" in a_regla4.causal_decision
    assert "Puesto 5/5" in a_regla5.causal_decision
    assert a_perdedor.estado_proceso == "NO_ADMITIDO"
    assert "Regla 5" in a_perdedor.causal_decision


def test_cruce_historico_pfu_corrimiento_cupo_y_segunda_opcion(db_session):
    """Verifica el cruce del Paso 7 (PFU, SANCION_DISCIPLINARIA, FALTA_RENOVACION), corrimiento de cupo y 2da opción."""
    prog_med = ProgramaAcademico(
        codigo="MED",
        nombre="Medicina",
        facultad="Facultad de Salud",
        cupos_ofertados=1,
        peso_ciencias_naturales=35.0,
        peso_sociales_ciudadanas=10.0,
        peso_matematicas=20.0,
        peso_lectura_critica=25.0,
        peso_ingles=10.0,
    )
    prog_enf = ProgramaAcademico(
        codigo="ENF",
        nombre="Enfermería",
        facultad="Facultad de Salud",
        cupos_ofertados=2,
        peso_ciencias_naturales=30.0,
        peso_sociales_ciudadanas=15.0,
        peso_matematicas=15.0,
        peso_lectura_critica=25.0,
        peso_ingles=15.0,
    )
    db_session.add_all([prog_med, prog_enf])
    db_session.commit()

    # Registrar antecedente P.F.U. para el aspirante con mayor puntaje en Medicina
    db_session.add(
        MockHistoricoUis(
            documento_identidad="3001",
            nombres_completos="Carlos PFU",
            tipo_inhabilidad="PFU",
            vigente=True,
            descripcion_causal="Pérdida de calidad de estudiante por bajo rendimiento académico (P.F.U.)",
            periodo_registro="2025-2",
        )
    )

    # Aspirante 1: Mejor puntaje en Medicina (90), pero tiene P.F.U. -> debe ser inhabilitado y correr el cupo
    asp_pfu = Aspirante(
        orden_inscripcion=1,
        documento_identidad="3001",
        nombres="Carlos",
        apellidos="PFU",
        correo="carlos@test.com",
        programa_opcion_1_id=prog_med.id,
        registro_snp="AC20243001",
        anio_examen=2024,
        puntaje_global_declarado=450.0,
        ciencias_naturales_declarado=90.0,
        sociales_ciudadanas_declarado=90.0,
        matematicas_declarado=90.0,
        lectura_critica_declarado=90.0,
        ingles_declarado=90.0,
        estado_proceso="HABILITADO",
    )

    # Aspirante 2: Segundo en Medicina (85) -> debe recibir el único cupo de Medicina por corrimiento
    asp_corrimiento = Aspirante(
        orden_inscripcion=2,
        documento_identidad="3002",
        nombres="Mariana",
        apellidos="Corrimiento",
        correo="mariana@test.com",
        programa_opcion_1_id=prog_med.id,
        programa_opcion_2_id=prog_enf.id,
        registro_snp="AC20243002",
        anio_examen=2024,
        puntaje_global_declarado=425.0,
        ciencias_naturales_declarado=85.0,
        sociales_ciudadanas_declarado=85.0,
        matematicas_declarado=85.0,
        lectura_critica_declarado=85.0,
        ingles_declarado=85.0,
        estado_proceso="HABILITADO",
    )

    # Aspirante 3: Tercero en Medicina (80), pero inscribió Enfermería en 2da opción -> entra a Enfermería en 2da opción
    asp_segunda_op = Aspirante(
        orden_inscripcion=3,
        documento_identidad="3003",
        nombres="Andrés",
        apellidos="Segunda Opción",
        correo="andres@test.com",
        programa_opcion_1_id=prog_med.id,
        programa_opcion_2_id=prog_enf.id,
        registro_snp="AC20243003",
        anio_examen=2024,
        puntaje_global_declarado=400.0,
        ciencias_naturales_declarado=80.0,
        sociales_ciudadanas_declarado=80.0,
        matematicas_declarado=80.0,
        lectura_critica_declarado=80.0,
        ingles_declarado=80.0,
        estado_proceso="HABILITADO",
    )

    db_session.add_all([asp_pfu, asp_corrimiento, asp_segunda_op])
    db_session.commit()

    res = ejecutar_pasos_6_y_7_seleccion_y_cruce_historico(db_session)
    assert res["inhabilitados_historico_uis"] == 1
    assert res["admitidos_primera_opcion"] == 1
    assert res["admitidos_segunda_opcion"] == 1

    db_session.refresh(asp_pfu)
    db_session.refresh(asp_corrimiento)
    db_session.refresh(asp_segunda_op)

    assert asp_pfu.estado_proceso == "INHABILITADO_HISTORICO_UIS"
    assert "PFU" in asp_pfu.causal_decision

    assert asp_corrimiento.estado_proceso == "ADMITIDO"
    assert asp_corrimiento.programa_admitido_id == prog_med.id
    assert asp_corrimiento.opcion_admitida == 1
    assert "corrimiento" in asp_corrimiento.causal_decision

    assert asp_segunda_op.estado_proceso == "ADMITIDO"
    assert asp_segunda_op.programa_admitido_id == prog_enf.id
    assert asp_segunda_op.opcion_admitida == 2

    # Verificar también cálculo directo de promedio ponderado
    assert calcular_promedio_ponderado(asp_corrimiento, prog_med) == 85.0

    # Verificar generación de listados oficiales (Pasos 8 y 10)
    listados = generar_listados_oficiales(db_session)
    assert listados["resumen"]["total_inscritos"] == 3
    assert listados["resumen"]["total_admitidos"] == 2
    assert listados["resumen"]["total_inscripciones_anuladas"] == 1
    assert listados["resumen"]["desglose_anuladas"]["INHABILITADO_HISTORICO_UIS"] == 1
    assert len(listados["admitidos"]) == 2
    assert len(listados["inscripciones_anuladas"]) == 1

    # Verificar Paso 12: asignación de código de estudiante UIS, hoja de vida y carta de admisión
    res_p12 = ejecutar_paso12_hoja_vida_y_cartas_admision(db_session, periodo_academico="2026-2")
    assert res_p12["total_cartas_expedidas"] == 2

    db_session.refresh(asp_corrimiento)
    assert asp_corrimiento.codigo_estudiante_uis is not None
    assert asp_corrimiento.codigo_estudiante_uis.startswith("2262")
    assert "HOJA DE VIDA ACADÉMICA PREGRADO UIS" in asp_corrimiento.hoja_vida_academica
    assert "CARTA OFICIAL DE ADMISIÓN" in asp_corrimiento.carta_admision
    assert "MEDICINA" in asp_corrimiento.carta_admision

