"""Motor determinista de reglas de negocio para el procedimiento PAR.01 de la DARA - UIS."""

from typing import Any, Dict, List, Optional
from sqlalchemy.orm import Session

from app.models import Aspirante, ProgramaAcademico

ANIO_CONVOCATORia_DEFAULT = 2026
PUNTAJE_MINIMO_AREA = 31.0
VIGENCIA_MAXIMA_ANIOS = 5
ANIO_MINIMO_SABER11 = 2012


def _normalizar_grupo_sisben(grupo_sisben: str) -> str:
    """Normaliza la cadena del grupo SISBÉN a una de las 4 categorías tarifarias UIS."""
    if not grupo_sisben:
        return "OTROS"
    g = grupo_sisben.strip().upper().replace("GRUPO", "").strip()
    if g == "A" or (g.startswith("A") and g[1:].isdigit()):
        return "A"
    if g == "B" or (g.startswith("B") and g[1:].isdigit()):
        return "B"
    if g in ("C1-C10", "C1 A C10"):
        return "C1-C10"
    if g.startswith("C") and g[1:].isdigit():
        subgrupo = int(g[1:])
        if 1 <= subgrupo <= 10:
            return "C1-C10"
    return "OTROS"


def liquidar_derechos_inscripcion(grupo_sisben: str, num_opciones: int = 1) -> Dict[str, Any]:
    """Calcula los derechos de inscripción en SMLMV según el nivel SISBÉN y número de opciones.

    Reglamento UIS (Sección 6 - PAR.01):
    - Máximo 2 programas académicos por proceso de admisión.
    - Primera opción: Grupo A=0.025, Grupo B=0.050, C1-C10=0.075, Otros=0.100 SMLMV.
    - Segunda opción: Grupo A=0.0125, Grupo B=0.0250, C1-C10=0.0375, Otros=0.0500 SMLMV.
    """
    if num_opciones < 1 or num_opciones > 2:
        raise ValueError(
            "Límite reglamentario excedido: Cada aspirante puede seleccionar entre 1 y máximo 2 "
            "opciones de programas académicos en un mismo proceso de admisión."
        )

    categoria = _normalizar_grupo_sisben(grupo_sisben)
    tabla_op1 = {
        "A": 0.025,
        "B": 0.050,
        "C1-C10": 0.075,
        "OTROS": 0.100,
    }
    tabla_op2 = {
        "A": 0.0125,
        "B": 0.0250,
        "C1-C10": 0.0375,
        "OTROS": 0.0500,
    }

    tarifa_op1 = tabla_op1[categoria]
    tarifa_op2 = tabla_op2[categoria] if num_opciones == 2 else 0.0
    total = round(tarifa_op1 + tarifa_op2, 4)

    return {
        "categoria_sisben": categoria,
        "num_opciones": num_opciones,
        "tarifa_opcion_1_smlmv": tarifa_op1,
        "tarifa_opcion_2_smlmv": tarifa_op2,
        "total_smlmv": total,
    }


def validar_aspirante_paso5(
    aspirante: Aspirante,
    anio_convocatoria: int = ANIO_CONVOCATORia_DEFAULT,
    modalidad: str = "PRESENCIAL",
) -> Dict[str, Any]:
    """Valida los requisitos mínimos del Paso 5 (PAR.01) para un aspirante individual.

    Verifica:
    1. Nivel educativo válido (diploma/acta de bachiller o certificado grado 11°).
    2. Vigencia del examen Saber 11°: año >= 2012 y antigüedad <= 5 años para presencial.
    3. Puntaje mínimo >= 31 puntos en cada una de las 5 áreas del Examen Saber 11°.
    """
    # Tomar puntajes verificados; si aún no están poblados, usar los declarados
    cn = aspirante.ciencias_naturales if aspirante.ciencias_naturales is not None else aspirante.ciencias_naturales_declarado
    sc = aspirante.sociales_ciudadanas if aspirante.sociales_ciudadanas is not None else aspirante.sociales_ciudadanas_declarado
    mat = aspirante.matematicas if aspirante.matematicas is not None else aspirante.matematicas_declarado
    lc = aspirante.lectura_critica if aspirante.lectura_critica is not None else aspirante.lectura_critica_declarado
    ing = aspirante.ingles if aspirante.ingles is not None else aspirante.ingles_declarado

    if aspirante.nivel_educativo_valido is False:
        causal = (
            "Inscripción anulada (Paso 5 - PAR.01): No acredita acta/diploma de bachiller "
            "ni certificación vigente de cursar undécimo grado."
        )
        aspirante.estado_proceso = "ANULADO_NIVEL_EDUCATIVO"
        aspirante.causal_decision = causal
        aspirante.append_log("PASO_5_REQUISITOS_MINIMOS", causal)
        return {"habilitado": False, "estado": aspirante.estado_proceso, "causal": causal}

    es_presencial = modalidad.upper() == "PRESENCIAL"

    # Validar vigencia del examen
    antiguedad = anio_convocatoria - aspirante.anio_examen
    if aspirante.anio_examen < ANIO_MINIMO_SABER11 or (es_presencial and antiguedad > VIGENCIA_MAXIMA_ANIOS):
        causal = (
            f"Inscripción anulada (Paso 5 - PAR.01): Examen Saber 11° presentado en {aspirante.anio_examen} "
            f"(antigüedad de {antiguedad} años respecto a la convocatoria {anio_convocatoria}), "
            f"superando la vigencia máxima reglamentaria de {VIGENCIA_MAXIMA_ANIOS} años (o previo a {ANIO_MINIMO_SABER11})."
        )
        aspirante.estado_proceso = "ANULADO_VIGENCIA_EXAMEN"
        aspirante.causal_decision = causal
        aspirante.append_log("PASO_5_REQUISITOS_MINIMOS", causal)
        return {"habilitado": False, "estado": aspirante.estado_proceso, "causal": causal}

    # Validar puntaje mínimo de 31 puntos en cada una de las 5 áreas (para programas presenciales)
    if es_presencial:
        areas = [
            ("Ciencias Naturales", cn),
            ("Sociales y Ciudadanas", sc),
            ("Matemáticas", mat),
            ("Lectura Crítica", lc),
            ("Inglés", ing),
        ]
        areas_incumplidas = [
            f"{nombre} ({valor:.1f} pts < {PUNTAJE_MINIMO_AREA:.0f})"
            for nombre, valor in areas
            if valor is None or valor < PUNTAJE_MINIMO_AREA
        ]
        if areas_incumplidas:
            detalle_areas = ", ".join(areas_incumplidas)
            causal = (
                f"Inscripción anulada (Paso 5 - PAR.01): Incumplimiento del puntaje mínimo de "
                f"{PUNTAJE_MINIMO_AREA:.0f} puntos por área en: {detalle_areas}."
            )
            aspirante.estado_proceso = "ANULADO_PUNTAJE_MINIMO"
            aspirante.causal_decision = causal
            aspirante.append_log("PASO_5_REQUISITOS_MINIMOS", causal)
            return {"habilitado": False, "estado": aspirante.estado_proceso, "causal": causal}

    causal = (
        f"Habilitado (Paso 5 - PAR.01): Cumple puntaje mínimo >= {PUNTAJE_MINIMO_AREA:.0f} en las 5 áreas "
        f"y vigencia del Examen Saber 11° ({aspirante.anio_examen}, antigüedad {antiguedad} años <= {VIGENCIA_MAXIMA_ANIOS})."
    )
    aspirante.estado_proceso = "HABILITADO"
    aspirante.causal_decision = causal
    aspirante.append_log("PASO_5_REQUISITOS_MINIMOS", causal)
    return {"habilitado": True, "estado": aspirante.estado_proceso, "causal": causal}


def ejecutar_paso5_validacion_puntajes_minimos(
    db: Session,
    anio_convocatoria: int = ANIO_CONVOCATORia_DEFAULT,
) -> Dict[str, Any]:
    """Ejecuta de forma masiva el Paso 5 sobre los aspirantes verificados con el ICFES."""
    aspirantes = (
        db.query(Aspirante)
        .filter(Aspirante.estado_proceso.in_(["INSCRITO", "VERIFICADO_ICFES", "HABILITADO"]))
        .order_by(Aspirante.orden_inscripcion.asc())
        .all()
    )

    habilitados = 0
    anulados_puntaje = 0
    anulados_vigencia = 0
    anulados_educativo = 0
    detalles: List[Dict[str, Any]] = []

    for asp in aspirantes:
        prog_op1 = db.query(ProgramaAcademico).filter(ProgramaAcademico.id == asp.programa_opcion_1_id).first()
        modalidad = prog_op1.modalidad if prog_op1 else "PRESENCIAL"
        res = validar_aspirante_paso5(asp, anio_convocatoria=anio_convocatoria, modalidad=modalidad)
        if res["habilitado"]:
            habilitados += 1
        elif res["estado"] == "ANULADO_PUNTAJE_MINIMO":
            anulados_puntaje += 1
        elif res["estado"] == "ANULADO_VIGENCIA_EXAMEN":
            anulados_vigencia += 1
        elif res["estado"] == "ANULADO_NIVEL_EDUCATIVO":
            anulados_educativo += 1

        detalles.append(
            {
                "aspirante_id": asp.id,
                "documento_identidad": asp.documento_identidad,
                "nombre_completo": f"{asp.nombres} {asp.apellidos}",
                "estado": res["estado"],
                "causal": res["causal"],
            }
        )

    db.commit()
    return {
        "etapa": "PASO_5_VALIDACION_PUNTAJES_Y_VIGENCIA",
        "anio_convocatoria": anio_convocatoria,
        "total_evaluados": len(aspirantes),
        "habilitados": habilitados,
        "anulados_puntaje_minimo": anulados_puntaje,
        "anulados_vigencia_examen": anulados_vigencia,
        "anulados_nivel_educativo": anulados_educativo,
        "detalles": detalles,
    }
