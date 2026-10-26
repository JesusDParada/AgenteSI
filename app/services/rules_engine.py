"""Motor determinista de reglas de negocio para el procedimiento PAR.01 de la DARA - UIS."""

from typing import Any, Dict, List, Optional, Tuple
from sqlalchemy.orm import Session

from app.models import Aspirante, MockHistoricoUis, ProgramaAcademico

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


def _obtener_puntajes_efectivos(aspirante: Aspirante) -> Dict[str, float]:
    """Obtiene los puntajes verificados del aspirante, o los declarados si aún no se han copiado."""
    return {
        "puntaje_global": (
            aspirante.puntaje_global
            if aspirante.puntaje_global is not None
            else aspirante.puntaje_global_declarado
        ),
        "ciencias_naturales": (
            aspirante.ciencias_naturales
            if aspirante.ciencias_naturales is not None
            else aspirante.ciencias_naturales_declarado
        ),
        "sociales_ciudadanas": (
            aspirante.sociales_ciudadanas
            if aspirante.sociales_ciudadanas is not None
            else aspirante.sociales_ciudadanas_declarado
        ),
        "matematicas": (
            aspirante.matematicas
            if aspirante.matematicas is not None
            else aspirante.matematicas_declarado
        ),
        "lectura_critica": (
            aspirante.lectura_critica
            if aspirante.lectura_critica is not None
            else aspirante.lectura_critica_declarado
        ),
        "ingles": (
            aspirante.ingles
            if aspirante.ingles is not None
            else aspirante.ingles_declarado
        ),
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
    pts = _obtener_puntajes_efectivos(aspirante)
    cn = pts["ciencias_naturales"]
    sc = pts["sociales_ciudadanas"]
    mat = pts["matematicas"]
    lc = pts["lectura_critica"]
    ing = pts["ingles"]

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


def calcular_promedio_ponderado(aspirante: Aspirante, programa: ProgramaAcademico) -> float:
    """Calcula el promedio ponderado del Examen Saber 11° según los pesos del programa académico."""
    pts = _obtener_puntajes_efectivos(aspirante)
    ponderado = (
        pts["ciencias_naturales"] * programa.peso_ciencias_naturales
        + pts["sociales_ciudadanas"] * programa.peso_sociales_ciudadanas
        + pts["matematicas"] * programa.peso_matematicas
        + pts["lectura_critica"] * programa.peso_lectura_critica
        + pts["ingles"] * programa.peso_ingles
    ) / 100.0
    return round(ponderado, 4)


def tiene_voto_valido_desempate(aspirante: Aspirante) -> bool:
    """Verifica la Regla 4 de desempate: voto válido en elecciones inmediatamente anteriores y mayor de edad."""
    edad = aspirante.edad if aspirante.edad is not None else 18
    return bool(aspirante.certificado_electoral_valido) and edad >= 18


def clave_ordenacion_merito(
    aspirante: Aspirante, puntaje_ponderado: float
) -> Tuple[float, float, float, float, int, int]:
    """Genera la tupla determinista de ordenación según mérito y las 5 reglas de desempate en cascada (Sección 4 PAR.01).

    Orden de prioridad ante empate en puntaje ponderado:
    1. Mayor Puntaje Global Saber 11°.
    2. Mayor puntaje en Lectura Crítica.
    3. Mayor puntaje en Sociales y Ciudadanas.
    4. Certificación de ejercicio del voto (si tiene edad legal para votar >= 18).
    5. Menor número de orden consecutivo de inscripción.
    """
    pts = _obtener_puntajes_efectivos(aspirante)
    voto_int = 1 if tiene_voto_valido_desempate(aspirante) else 0
    return (
        -round(puntaje_ponderado, 4),
        -round(float(pts["puntaje_global"]), 4),
        -round(float(pts["lectura_critica"]), 4),
        -round(float(pts["sociales_ciudadanas"]), 4),
        -voto_int,
        int(aspirante.orden_inscripcion),
    )


def explicar_criterio_desempate(
    asp_a: Aspirante,
    asp_b: Aspirante,
    ponderado_a: float,
    ponderado_b: float,
) -> Optional[str]:
    """Si dos aspirantes empatan en puntaje ponderado, devuelve la regla exacta de desempate que los diferencia."""
    if round(ponderado_a, 4) != round(ponderado_b, 4):
        return None

    pts_a = _obtener_puntajes_efectivos(asp_a)
    pts_b = _obtener_puntajes_efectivos(asp_b)

    if pts_a["puntaje_global"] != pts_b["puntaje_global"]:
        return (
            f"Desempate Regla 1 (Puntaje Global Saber 11°): "
            f"{pts_a['puntaje_global']:.1f} vs {pts_b['puntaje_global']:.1f} de {asp_b.nombres} {asp_b.apellidos}"
        )
    if pts_a["lectura_critica"] != pts_b["lectura_critica"]:
        return (
            f"Desempate Regla 2 (Lectura Crítica): "
            f"{pts_a['lectura_critica']:.1f} vs {pts_b['lectura_critica']:.1f} de {asp_b.nombres} {asp_b.apellidos}"
        )
    if pts_a["sociales_ciudadanas"] != pts_b["sociales_ciudadanas"]:
        return (
            f"Desempate Regla 3 (Sociales y Ciudadanas): "
            f"{pts_a['sociales_ciudadanas']:.1f} vs {pts_b['sociales_ciudadanas']:.1f} de {asp_b.nombres} {asp_b.apellidos}"
        )
    voto_a = tiene_voto_valido_desempate(asp_a)
    voto_b = tiene_voto_valido_desempate(asp_b)
    if voto_a != voto_b:
        return (
            f"Desempate Regla 4 (Certificado Electoral validado en mayor de edad): "
            f"{'Presentó voto válido' if voto_a else 'Sin certificado electoral válido'} vs {asp_b.nombres} {asp_b.apellidos}"
        )
    return (
        f"Desempate Regla 5 (Orden consecutivo de inscripción): "
        f"Turno #{asp_a.orden_inscripcion} vs Turno #{asp_b.orden_inscripcion} de {asp_b.nombres} {asp_b.apellidos}"
    )


def verificar_inhabilidad_historica_paso7(
    db: Session, aspirante: Aspirante
) -> Optional[MockHistoricoUis]:
    """Consulta el archivo histórico de hojas de vida UIS (Paso 7) para detectar P.F.U. o sanciones vigentes."""
    return (
        db.query(MockHistoricoUis)
        .filter(
            MockHistoricoUis.documento_identidad == aspirante.documento_identidad,
            MockHistoricoUis.vigente.is_(True),
        )
        .first()
    )


def ejecutar_pasos_6_y_7_seleccion_y_cruce_historico(
    db: Session,
    programa_id: Optional[int] = None,
) -> Dict[str, Any]:
    """Ejecuta los Pasos 6 y 7 (PAR.01): ponderación, desempate por las 5 reglas, asignación 1ra/2da opción y cruce P.F.U."""
    query_prog = db.query(ProgramaAcademico)
    if programa_id is not None:
        query_prog = query_prog.filter(ProgramaAcademico.id == programa_id)
    programas = query_prog.order_by(ProgramaAcademico.id.asc()).all()
    programas_map = {p.id: p for p in db.query(ProgramaAcademico).all()}

    # Considerar aspirantes en estado HABILITADO (o ADMITIDO/NO_ADMITIDO si se re-ejecuta la selección)
    aspirantes_elegibles = (
        db.query(Aspirante)
        .filter(Aspirante.estado_proceso.in_(["HABILITADO", "ADMITIDO", "NO_ADMITIDO"]))
        .all()
    )

    # Reiniciar estado temporal de selección para cálculo determinista limpio
    for asp in aspirantes_elegibles:
        if programa_id is None or asp.programa_opcion_1_id == programa_id or asp.programa_opcion_2_id == programa_id:
            asp.estado_proceso = "HABILITADO"
            asp.programa_admitido_id = None
            asp.opcion_admitida = None

        prog1 = programas_map.get(asp.programa_opcion_1_id)
        if prog1:
            asp.puntaje_ponderado_op1 = calcular_promedio_ponderado(asp, prog1)
        if asp.programa_opcion_2_id and asp.programa_opcion_2_id in programas_map:
            prog2 = programas_map[asp.programa_opcion_2_id]
            asp.puntaje_ponderado_op2 = calcular_promedio_ponderado(asp, prog2)

    cupos_restantes_por_programa: Dict[int, int] = {
        p.id: p.cupos_ofertados for p in programas
    }
    resumen_programas: List[Dict[str, Any]] = []
    inhabilitados_historico = 0
    admitidos_op1 = 0
    admitidos_op2 = 0

    # ==========================================================
    # FASE 1: Asignación en Primera Opción + Cruce Paso 7 (P.F.U.)
    # ==========================================================
    for prog in programas:
        candidatos_op1 = [
            a
            for a in aspirantes_elegibles
            if a.programa_opcion_1_id == prog.id and a.estado_proceso == "HABILITADO"
        ]
        candidatos_op1.sort(
            key=lambda a: clave_ordenacion_merito(a, a.puntaje_ponderado_op1 or 0.0)
        )

        admitidos_prog_op1: List[Aspirante] = []
        corrimientos_pfu: List[str] = []

        for idx, asp in enumerate(candidatos_op1):
            if cupos_restantes_por_programa[prog.id] <= 0:
                break

            # Paso 7: Cruce contra archivo histórico UIS para los preseleccionados
            antecedente = verificar_inhabilidad_historica_paso7(db, asp)
            if antecedente is not None:
                asp.estado_proceso = "INHABILITADO_HISTORICO_UIS"
                asp.programa_admitido_id = None
                asp.opcion_admitida = None
                causal = (
                    f"Inscripción anulada en Paso 7 (Archivo Histórico UIS - {antecedente.tipo_inhabilidad}): "
                    f"Preseleccionado por mérito en {prog.nombre} (ponderado {asp.puntaje_ponderado_op1:.2f}), "
                    f"pero registra antecedente vigente ({antecedente.descripcion_causal}, periodo {antecedente.periodo_registro}). "
                    f"Se aplica corrimiento de cupo al siguiente en lista de mérito."
                )
                asp.causal_decision = causal
                asp.append_log("PASO_7_HISTORICO_UIS", causal)
                inhabilitados_historico += 1
                corrimientos_pfu.append(f"{asp.nombres} {asp.apellidos} ({antecedente.tipo_inhabilidad})")
                continue

            # No tiene inhabilidad: asignar cupo en primera opción
            cupos_restantes_por_programa[prog.id] -= 1
            puesto = prog.cupos_ofertados - cupos_restantes_por_programa[prog.id]
            asp.estado_proceso = "ADMITIDO"
            asp.programa_admitido_id = prog.id
            asp.opcion_admitida = 1
            admitidos_op1 += 1
            admitidos_prog_op1.append(asp)

            notas_extra: List[str] = []
            # Verificar si empató en puntaje ponderado con el candidato inmediatamente siguiente o anterior en orden de mérito
            vecinos: List[Aspirante] = []
            if idx + 1 < len(candidatos_op1):
                vecinos.append(candidatos_op1[idx + 1])
            if idx - 1 >= 0:
                vecinos.append(candidatos_op1[idx - 1])
            for otro in vecinos:
                if round(otro.puntaje_ponderado_op1 or 0.0, 4) == round(asp.puntaje_ponderado_op1 or 0.0, 4):
                    exp = explicar_criterio_desempate(
                        asp, otro, asp.puntaje_ponderado_op1 or 0.0, otro.puntaje_ponderado_op1 or 0.0
                    )
                    if exp:
                        notas_extra.append(exp)
                        break

            if corrimientos_pfu and puesto == prog.cupos_ofertados:
                notas_extra.append(
                    f"Cupo asignado por corrimiento de lista de mérito tras inhabilidad histórica de: {', '.join(corrimientos_pfu)}"
                )

            extra_str = f" [{'; '.join(notas_extra)}]" if notas_extra else ""
            causal = (
                f"Admitido en 1ra opción a {prog.nombre} (Puesto {puesto}/{prog.cupos_ofertados}) "
                f"con promedio ponderado {asp.puntaje_ponderado_op1:.4f}.{extra_str}"
            )
            asp.causal_decision = causal
            asp.append_log("PASO_6_7_SELECCION_OP1", causal)

        resumen_programas.append(
            {
                "programa_id": prog.id,
                "codigo": prog.codigo,
                "nombre": prog.nombre,
                "cupos_ofertados": prog.cupos_ofertados,
                "admitidos_primera_opcion": len(admitidos_prog_op1),
                "corrimientos_por_historico": corrimientos_pfu,
            }
        )

    # ==========================================================
    # FASE 2: Segunda Opción sobre cupos remanentes + Paso 7
    # ==========================================================
    for idx_prog, prog in enumerate(programas):
        if cupos_restantes_por_programa[prog.id] <= 0:
            resumen_programas[idx_prog]["admitidos_segunda_opcion"] = 0
            resumen_programas[idx_prog]["cupos_remanentes"] = 0
            continue

        candidatos_op2 = [
            a
            for a in aspirantes_elegibles
            if a.programa_opcion_2_id == prog.id and a.estado_proceso == "HABILITADO"
        ]
        candidatos_op2.sort(
            key=lambda a: clave_ordenacion_merito(a, a.puntaje_ponderado_op2 or 0.0)
        )

        admitidos_prog_op2 = 0
        for asp in candidatos_op2:
            if cupos_restantes_por_programa[prog.id] <= 0:
                break

            antecedente = verificar_inhabilidad_historica_paso7(db, asp)
            if antecedente is not None:
                asp.estado_proceso = "INHABILITADO_HISTORICO_UIS"
                asp.programa_admitido_id = None
                asp.opcion_admitida = None
                causal = (
                    f"Inscripción anulada en Paso 7 (Archivo Histórico UIS - {antecedente.tipo_inhabilidad}): "
                    f"Preseleccionado en 2da opción en {prog.nombre} (ponderado {asp.puntaje_ponderado_op2:.2f}), "
                    f"pero registra antecedente vigente ({antecedente.descripcion_causal})."
                )
                asp.causal_decision = causal
                asp.append_log("PASO_7_HISTORICO_UIS", causal)
                inhabilitados_historico += 1
                continue

            cupos_restantes_por_programa[prog.id] -= 1
            puesto = prog.cupos_ofertados - cupos_restantes_por_programa[prog.id]
            asp.estado_proceso = "ADMITIDO"
            asp.programa_admitido_id = prog.id
            asp.opcion_admitida = 2
            admitidos_op2 += 1
            admitidos_prog_op2 += 1

            causal = (
                f"Admitido en 2da opción a {prog.nombre} sobre cupos remanentes "
                f"(Puesto {puesto}/{prog.cupos_ofertados}) con promedio ponderado {asp.puntaje_ponderado_op2:.4f}."
            )
            asp.causal_decision = causal
            asp.append_log("PASO_6_7_SELECCION_OP2", causal)

        resumen_programas[idx_prog]["admitidos_segunda_opcion"] = admitidos_prog_op2
        resumen_programas[idx_prog]["cupos_remanentes"] = cupos_restantes_por_programa[prog.id]

    # ==========================================================
    # FASE 3: Marcar NO_ADMITIDO a quienes no alcanzaron cupo
    # ==========================================================
    no_admitidos = 0
    for asp in aspirantes_elegibles:
        if asp.estado_proceso == "HABILITADO":
            prog1 = programas_map.get(asp.programa_opcion_1_id)
            if programa_id is not None and asp.programa_opcion_1_id != programa_id and asp.programa_opcion_2_id != programa_id:
                continue

            # Buscar último admitido en orden de mérito del programa de 1ra opción para explicar corte/desempate
            admitidos_mismo_prog = [
                a
                for a in aspirantes_elegibles
                if a.programa_admitido_id == asp.programa_opcion_1_id and a.estado_proceso == "ADMITIDO"
            ]
            admitidos_mismo_prog.sort(
                key=lambda a: (
                    a.opcion_admitida or 1,
                    clave_ordenacion_merito(
                        a,
                        (a.puntaje_ponderado_op1 if a.opcion_admitida == 1 else a.puntaje_ponderado_op2) or 0.0,
                    ),
                )
            )
            detalle_corte = ""
            if admitidos_mismo_prog:
                ultimo_adm = admitidos_mismo_prog[-1]
                pond_ult = (
                    ultimo_adm.puntaje_ponderado_op1
                    if ultimo_adm.opcion_admitida == 1
                    else ultimo_adm.puntaje_ponderado_op2
                ) or 0.0
                exp_empate = explicar_criterio_desempate(
                    ultimo_adm, asp, pond_ult, asp.puntaje_ponderado_op1 or 0.0
                )
                if exp_empate:
                    detalle_corte = f" Superado en cierre de cupo por {ultimo_adm.nombres} {ultimo_adm.apellidos} mediante {exp_empate}."
                else:
                    detalle_corte = f" Puntaje de cierre del programa: {pond_ult:.4f}."

            asp.estado_proceso = "NO_ADMITIDO"
            nombre_prog1 = prog1.nombre if prog1 else f"ID {asp.programa_opcion_1_id}"
            causal = (
                f"No admitido por agotamiento de cupos ofertados en {nombre_prog1} "
                f"(promedio ponderado obtenido: {(asp.puntaje_ponderado_op1 or 0.0):.4f}).{detalle_corte}"
            )
            asp.causal_decision = causal
            asp.append_log("PASO_6_NO_ADMITIDO", causal)
            no_admitidos += 1

    db.commit()
    return {
        "etapa": "PASOS_6_Y_7_SELECCION_Y_CRUCE_HISTORICO",
        "admitidos_primera_opcion": admitidos_op1,
        "admitidos_segunda_opcion": admitidos_op2,
        "total_admitidos": admitidos_op1 + admitidos_op2,
        "inhabilitados_historico_uis": inhabilitados_historico,
        "no_admitidos": no_admitidos,
        "programas": resumen_programas,
    }


ESTADOS_ANULADOS = (
    "INCONSISTENCIA_ICFES",
    "ANULADO_PUNTAJE_MINIMO",
    "ANULADO_VIGENCIA_EXAMEN",
    "ANULADO_NIVEL_EDUCATIVO",
    "INHABILITADO_HISTORICO_UIS",
)


def _serializar_item_listado(
    asp: Aspirante, programas_map: Dict[int, ProgramaAcademico]
) -> Dict[str, Any]:
    prog1 = programas_map.get(asp.programa_opcion_1_id)
    prog2 = programas_map.get(asp.programa_opcion_2_id) if asp.programa_opcion_2_id else None
    prog_adm = programas_map.get(asp.programa_admitido_id) if asp.programa_admitido_id else None
    return {
        "aspirante_id": asp.id,
        "orden_inscripcion": asp.orden_inscripcion,
        "documento_identidad": asp.documento_identidad,
        "nombre_completo": f"{asp.nombres} {asp.apellidos}",
        "correo": asp.correo,
        "registro_snp": asp.registro_snp,
        "anio_examen": asp.anio_examen,
        "programa_opcion_1": prog1.nombre if prog1 else None,
        "programa_opcion_2": prog2.nombre if prog2 else None,
        "programa_admitido": prog_adm.nombre if prog_adm else None,
        "facultad_admitido": prog_adm.facultad if prog_adm else (prog1.facultad if prog1 else None),
        "opcion_admitida": asp.opcion_admitida,
        "puntaje_ponderado_op1": asp.puntaje_ponderado_op1,
        "puntaje_ponderado_op2": asp.puntaje_ponderado_op2,
        "puntaje_global": (
            asp.puntaje_global if asp.puntaje_global is not None else asp.puntaje_global_declarado
        ),
        "estado_proceso": asp.estado_proceso,
        "causal_decision": asp.causal_decision,
        "codigo_estudiante_uis": asp.codigo_estudiante_uis,
    }


def generar_listados_oficiales(
    db: Session, programa_id: Optional[int] = None
) -> Dict[str, Any]:
    """Genera los listados oficiales de Admitidos, No Admitidos e Inscripciones Anuladas (Pasos 8 y 10 PAR.01)."""
    programas_map = {p.id: p for p in db.query(ProgramaAcademico).all()}
    todos = db.query(Aspirante).order_by(Aspirante.orden_inscripcion.asc()).all()

    if programa_id is not None:
        todos = [
            a
            for a in todos
            if a.programa_opcion_1_id == programa_id
            or a.programa_opcion_2_id == programa_id
            or a.programa_admitido_id == programa_id
        ]

    admitidos_raw = [a for a in todos if a.estado_proceso == "ADMITIDO"]
    admitidos_raw.sort(
        key=lambda a: (
            a.programa_admitido_id or 0,
            a.opcion_admitida or 1,
            clave_ordenacion_merito(
                a,
                (a.puntaje_ponderado_op1 if a.opcion_admitida == 1 else a.puntaje_ponderado_op2) or 0.0,
            ),
        )
    )
    no_admitidos_raw = [a for a in todos if a.estado_proceso == "NO_ADMITIDO"]
    no_admitidos_raw.sort(
        key=lambda a: clave_ordenacion_merito(a, a.puntaje_ponderado_op1 or 0.0)
    )
    anulados_raw = [a for a in todos if a.estado_proceso in ESTADOS_ANULADOS]

    conteo_causales_anulacion = {
        "INCONSISTENCIA_ICFES": sum(1 for a in anulados_raw if a.estado_proceso == "INCONSISTENCIA_ICFES"),
        "ANULADO_PUNTAJE_MINIMO": sum(1 for a in anulados_raw if a.estado_proceso == "ANULADO_PUNTAJE_MINIMO"),
        "ANULADO_VIGENCIA_EXAMEN": sum(1 for a in anulados_raw if a.estado_proceso == "ANULADO_VIGENCIA_EXAMEN"),
        "ANULADO_NIVEL_EDUCATIVO": sum(1 for a in anulados_raw if a.estado_proceso == "ANULADO_NIVEL_EDUCATIVO"),
        "INHABILITADO_HISTORICO_UIS": sum(
            1 for a in anulados_raw if a.estado_proceso == "INHABILITADO_HISTORICO_UIS"
        ),
    }

    return {
        "etapa": "PASOS_8_Y_10_LISTADOS_OFICIALES",
        "resumen": {
            "total_inscritos": len(todos),
            "total_admitidos": len(admitidos_raw),
            "total_no_admitidos": len(no_admitidos_raw),
            "total_inscripciones_anuladas": len(anulados_raw),
            "desglose_anuladas": conteo_causales_anulacion,
        },
        "admitidos": [_serializar_item_listado(a, programas_map) for a in admitidos_raw],
        "no_admitidos": [_serializar_item_listado(a, programas_map) for a in no_admitidos_raw],
        "inscripciones_anuladas": [_serializar_item_listado(a, programas_map) for a in anulados_raw],
    }


def ejecutar_paso12_hoja_vida_y_cartas_admision(
    db: Session, periodo_academico: str = "2026-2"
) -> Dict[str, Any]:
    """Ejecuta el Paso 12 (PAR.01): Asigna código de estudiante UIS, abre hoja de vida académica y expide carta de admisión."""
    programas_map = {p.id: p for p in db.query(ProgramaAcademico).all()}
    admitidos = (
        db.query(Aspirante)
        .filter(Aspirante.estado_proceso == "ADMITIDO")
        .order_by(Aspirante.programa_admitido_id.asc(), Aspirante.orden_inscripcion.asc())
        .all()
    )

    expediciones: List[Dict[str, Any]] = []
    prefijo_periodo = periodo_academico.replace("-", "")[-3:]  # ej. "262" para 2026-2

    for idx, asp in enumerate(admitidos, start=1):
        prog = programas_map.get(asp.programa_admitido_id or asp.programa_opcion_1_id)
        nombre_prog = prog.nombre if prog else "Programa de Pregrado UIS"
        facultad_prog = prog.facultad if prog else "Facultad UIS"
        codigo_prog = prog.codigo if prog else "PREG"

        if not asp.codigo_estudiante_uis:
            asp.codigo_estudiante_uis = f"2{prefijo_periodo}{asp.id:03d}"

        ponderado_ingreso = (
            asp.puntaje_ponderado_op1
            if asp.opcion_admitida == 1
            else (asp.puntaje_ponderado_op2 or asp.puntaje_ponderado_op1 or 0.0)
        )

        hoja_vida = (
            f"=== HOJA DE VIDA ACADÉMICA PREGRADO UIS ===\n"
            f"Código Estudiante UIS : {asp.codigo_estudiante_uis}\n"
            f"Estudiante            : {asp.nombres} {asp.apellidos}\n"
            f"Documento Identidad   : {asp.tipo_documento} {asp.documento_identidad}\n"
            f"Programa Académico    : {nombre_prog} ({codigo_prog})\n"
            f"Facultad              : {facultad_prog}\n"
            f"Sede / Modalidad      : Sede Bucaramanga - {prog.modalidad if prog else 'PRESENCIAL'}\n"
            f"Periodo de Ingreso    : {periodo_academico}\n"
            f"Opción de Admisión    : Opción {asp.opcion_admitida or 1}\n"
            f"Promedio Ponderado    : {ponderado_ingreso:.4f}\n"
            f"Registro SNP ICFES    : {asp.registro_snp} (Año {asp.anio_examen})\n"
            f"Estado Académico      : ACTIVO - ADMITIDO PENDIENTE LEGALIZACIÓN MATRÍCULA (Paso 13 PAR.01)"
        )
        asp.hoja_vida_academica = hoja_vida

        carta = (
            f"UNIVERSIDAD INDUSTRIAL DE SANTANDER (UIS)\n"
            f"DIRECCIÓN DE ADMISIONES Y REGISTRO ACADÉMICO - DARA\n"
            f"Bucaramanga, Proceso de Admisión Pregrado {periodo_academico}\n\n"
            f"Asunto: CARTA OFICIAL DE ADMISIÓN Y APERTURA DE HOJA DE VIDA ACADÉMICA\n\n"
            f"Apreciado(a) {asp.nombres} {asp.apellidos} ({asp.tipo_documento} {asp.documento_identidad}):\n\n"
            f"La Dirección de Admisiones y Registro Académico (DARA) le informa que, una vez surtido el "
            f"Procedimiento de Selección de Aspirantes a Programas Académicos de Pregrado (PAR.01) y aprobados "
            f"los listados definitivos mediante acta formal del Consejo Académico, usted ha sido ADMITIDO(A) "
            f"al programa de {nombre_prog.upper()} adscrito a la {facultad_prog}.\n\n"
            f"DATOS OFICIALES DE SU REGISTRO ACADÉMICO:\n"
            f"- Código Único de Estudiante UIS : {asp.codigo_estudiante_uis}\n"
            f"- Programa Admitido              : {nombre_prog} (Opción {asp.opcion_admitida or 1})\n"
            f"- Promedio Ponderado Saber 11°   : {ponderado_ingreso:.4f}\n"
            f"- Detalle de Selección           : {asp.causal_decision}\n\n"
            f"INSTRUCCIONES PARA LA LEGALIZACIÓN DE MATRÍCULA (PASO 13 - PAR.01):\n"
            f"1. Ingrese al portal web institucional (www.uis.edu.co) con su código de estudiante {asp.codigo_estudiante_uis}.\n"
            f"2. Cargue la documentación exigida para liquidación y perfeccionamiento de matrícula dentro de las fechas "
            f"fijadas por el calendario académico.\n"
            f"3. En caso de requerir reserva de cupo por causal reglamentaria, radique la solicitud formal ante la DARA "
            f"antes del cierre del periodo de matrícula ordinaria.\n\n"
            f"Atentamente,\n"
            f"Coordinación de Admisiones - Dirección de Admisiones y Registro Académico (DARA)\n"
            f"Universidad Industrial de Santander"
        )
        asp.carta_admision = carta
        asp.append_log(
            "PASO_12_HOJA_VIDA_Y_CARTA",
            f"Código UIS asignado: {asp.codigo_estudiante_uis}. Hoja de vida abierta y carta de admisión expedida para {nombre_prog}.",
        )

        expediciones.append(
            {
                "aspirante_id": asp.id,
                "documento_identidad": asp.documento_identidad,
                "nombre_completo": f"{asp.nombres} {asp.apellidos}",
                "codigo_estudiante_uis": asp.codigo_estudiante_uis,
                "programa_admitido": nombre_prog,
                "hoja_vida_academica": hoja_vida,
                "carta_admision": carta,
            }
        )

    db.commit()
    return {
        "etapa": "PASO_12_GENERACION_HOJA_VIDA_Y_CARTA_ADMISION",
        "periodo_academico": periodo_academico,
        "total_cartas_expedidas": len(expediciones),
        "expediciones": expediciones,
    }

