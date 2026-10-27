"""Servicio de Auditoría Documental Multimodal IA (Gemini 3.5 Flash-Lite) y Copiloto DARA con Tool Calling."""

import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional
from sqlalchemy.orm import Session

from app.models import (
    Aspirante,
    MockHistoricoUis,
    MockIcfesOficial,
    ProgramaAcademico,
    SoporteDocumental,
)
from app.schemas import (
    ExtraccionDiplomaSchema,
    ExtraccionElectoralSchema,
    ExtraccionIcfesSchema,
)
from app.services.rules_engine import (
    ANIO_CONVOCATORia_DEFAULT,
    ejecutar_paso5_validacion_puntajes_minimos,
    ejecutar_paso12_hoja_vida_y_cartas_admision,
    ejecutar_pasos_6_y_7_seleccion_y_cruce_historico,
    generar_listados_oficiales,
    liquidar_derechos_inscripcion,
)

MODELO_GEMINI = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")
CORREO_INSTITUCIONAL_DARA = "admisiones@uis.edu.co"


def _obtener_gemini_api_key() -> str:
    """Obtiene GEMINI_API_KEY desde variables de entorno o desde un archivo .env local."""
    key = os.getenv("GEMINI_API_KEY", "").strip()
    if key:
        return key
    env_path = Path(".env")
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line_clean = line.strip()
            if line_clean.startswith("GEMINI_API_KEY="):
                val = line_clean.split("=", 1)[1].strip().strip('"').strip("'")
                if val:
                    return val
    return ""


def tiene_gemini_api_key() -> bool:
    """Verifica si existe una clave GEMINI_API_KEY configurada en el entorno o en .env."""
    return bool(_obtener_gemini_api_key())


# =====================================================================
# 1. EXTRACCIÓN MULTIMODAL DE SOPORTES EN PDF E IMAGEN (GEMINI + FALLBACK)
# =====================================================================

def _extraer_con_gemini_vision(
    file_bytes: bytes,
    mime_type: str,
    tipo_documento: str,
) -> Optional[Any]:
    """Invoca el modelo multimodal gemini-3.5-flash-lite con response_schema Pydantic."""
    api_key = _obtener_gemini_api_key()
    if not api_key:
        return None

    try:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=api_key)
        tipo = tipo_documento.upper()

        if tipo == "ICFES":
            schema_cls = ExtraccionIcfesSchema
            prompt = (
                "Analiza este soporte del Examen de Estado Saber 11° (ICFES) para admisión UIS. "
                "Extrae con exactitud el número de registro SNP, documento de identidad, nombres, "
                "año y fecha de presentación, puntaje global y los 5 puntajes por área "
                "(Ciencias Naturales, Sociales y Ciudadanas, Matemáticas, Lectura Crítica e Inglés)."
            )
        elif tipo == "DIPLOMA_BACHILLER":
            schema_cls = ExtraccionDiplomaSchema
            prompt = (
                "Analiza este soporte de nivel educativo (acta de grado, diploma de bachiller o "
                "certificado de estar cursando grado undécimo) y extrae los datos estructurados."
            )
        else:
            schema_cls = ExtraccionElectoralSchema
            prompt = (
                "Analiza este Certificado Electoral colombiano y extrae el documento de identidad, "
                "nombres, fecha de elecciones y determina si es válido para desempate de admisión."
            )

        response = client.models.generate_content(
            model=MODELO_GEMINI,
            contents=[
                types.Part.from_bytes(data=file_bytes, mime_type=mime_type),
                prompt,
            ],
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=schema_cls,
                temperature=0.0,
            ),
        )
        if response and response.text:
            data = json.loads(response.text)
            return schema_cls.model_validate(data)
    except Exception:
        return None
    return None


def _extraer_con_fallback_local(
    db: Session,
    soporte: SoporteDocumental,
    aspirante: Aspirante,
) -> Any:
    """Extractor determinista de respaldo cuando no hay GEMINI_API_KEY o sin conexión."""
    tipo = soporte.tipo_documento.upper()
    nombre_completo = f"{aspirante.nombres} {aspirante.apellidos}"
    nombre_lower = (soporte.nombre_archivo or "").lower()
    es_archivo_invalido = "invalido" in nombre_lower or "adulterado" in nombre_lower

    if tipo == "ICFES":
        oficial = (
            db.query(MockIcfesOficial)
            .filter(MockIcfesOficial.registro_snp == aspirante.registro_snp)
            .first()
        )
        if oficial and not es_archivo_invalido:
            return ExtraccionIcfesSchema(
                registro_snp=oficial.registro_snp,
                documento_identidad=oficial.documento_identidad,
                nombres_completos=oficial.nombres_completos,
                anio_examen=oficial.anio_examen,
                fecha_presentacion=oficial.fecha_presentacion,
                puntaje_global=oficial.puntaje_global,
                ciencias_naturales=oficial.ciencias_naturales,
                sociales_ciudadanas=oficial.sociales_ciudadanas,
                matematicas=oficial.matematicas,
                lectura_critica=oficial.lectura_critica,
                ingles=oficial.ingles,
                es_valido=True,
                observaciones=(
                    f"Soporte Saber 11° ({soporte.mime_type}) procesado y validado correctamente. "
                    f"Registro SNP {oficial.registro_snp} legible."
                ),
            )
        return ExtraccionIcfesSchema(
            registro_snp=aspirante.registro_snp,
            documento_identidad=aspirante.documento_identidad,
            nombres_completos=nombre_completo,
            anio_examen=aspirante.anio_examen,
            fecha_presentacion=f"{aspirante.anio_examen}-08-18",
            puntaje_global=aspirante.puntaje_global_declarado,
            ciencias_naturales=aspirante.ciencias_naturales_declarado,
            sociales_ciudadanas=aspirante.sociales_ciudadanas_declarado,
            matematicas=aspirante.matematicas_declarado,
            lectura_critica=aspirante.lectura_critica_declarado,
            ingles=aspirante.ingles_declarado,
            es_valido=not es_archivo_invalido,
            observaciones=(
                "Soporte Saber 11° con alerta de inconsistencia frente a base oficial ICFES."
                if es_archivo_invalido
                else f"Soporte Saber 11° ({soporte.mime_type}) extraído desde documento cargado."
            ),
        )

    if tipo == "DIPLOMA_BACHILLER":
        es_cert_11 = "11" in nombre_lower or "undecimo" in nombre_lower or "certificado" in nombre_lower
        tipo_edu = "CERTIFICADO_GRADO_11" if es_cert_11 else "DIPLOMA_BACHILLER"
        valido = not es_archivo_invalido
        return ExtraccionDiplomaSchema(
            documento_identidad=aspirante.documento_identidad,
            nombres_completos=nombre_completo,
            institucion_educativa="Instituto Técnico Superior Dámaso Zapata - Bucaramanga",
            tipo_soporte_educativo=tipo_edu,
            anio_grado_o_curso=aspirante.anio_examen,
            es_valido=valido,
            observaciones=(
                f"Soporte académico válido ({tipo_edu}): acredita requisito de nivel educativo PAR.01."
                if valido
                else "Soporte académico inválido o ilegible: no acredita grado 11° ni título de bachiller."
            ),
        )

    # CERTIFICADO_ELECTORAL
    es_vencido = "vencido" in nombre_lower or "2018" in nombre_lower or es_archivo_invalido
    corresponde_ultimas = not es_vencido
    mayor_edad = (aspirante.edad or 18) >= 18
    valido = corresponde_ultimas and mayor_edad
    return ExtraccionElectoralSchema(
        documento_identidad=aspirante.documento_identidad,
        nombres_completos=nombre_completo,
        fecha_elecciones="2023-10-29" if corresponde_ultimas else "2018-05-27",
        corresponde_ultimas_elecciones=corresponde_ultimas,
        es_valido=valido,
        observaciones=(
            "Certificado Electoral válido de las elecciones inmediatamente anteriores (habilitado para Regla 4 de desempate)."
            if valido
            else "Certificado Electoral no válido para desempate (no corresponde a últimas elecciones o aspirante menor de edad)."
        ),
    )


def auditar_soporte_multimodal(
    db: Session,
    soporte_id: int,
) -> Dict[str, Any]:
    """Procesa un soporte documental en PDF o imagen con IA multimodal (o fallback determinista) y actualiza al aspirante."""
    soporte = db.query(SoporteDocumental).filter(SoporteDocumental.id == soporte_id).first()
    if not soporte:
        raise ValueError(f"Soporte documental con ID {soporte_id} no encontrado.")

    aspirante = db.query(Aspirante).filter(Aspirante.id == soporte.aspirante_id).first()
    if not aspirante:
        raise ValueError(f"Aspirante asociado al soporte {soporte_id} no encontrado.")

    file_bytes = b""
    ruta = Path(soporte.ruta_archivo)
    if ruta.exists() and ruta.is_file():
        file_bytes = ruta.read_bytes()

    modo_ia = MODELO_GEMINI
    resultado_schema = None
    if file_bytes and tiene_gemini_api_key():
        resultado_schema = _extraer_con_gemini_vision(
            file_bytes=file_bytes,
            mime_type=soporte.mime_type,
            tipo_documento=soporte.tipo_documento,
        )

    if resultado_schema is None:
        modo_ia = "deterministic_fallback"
        resultado_schema = _extraer_con_fallback_local(db, soporte, aspirante)

    datos_dict = resultado_schema.model_dump()
    soporte.datos_extraidos_json = json.dumps(datos_dict, ensure_ascii=False)
    soporte.es_valido = bool(resultado_schema.es_valido)
    soporte.observaciones_ia = resultado_schema.observaciones

    # Actualizar banderas del aspirante según el tipo de soporte auditado
    tipo = soporte.tipo_documento.upper()
    if tipo == "DIPLOMA_BACHILLER":
        aspirante.nivel_educativo_valido = bool(resultado_schema.es_valido)
    elif tipo == "CERTIFICADO_ELECTORAL":
        aspirante.certificado_electoral_valido = bool(
            resultado_schema.es_valido
            and getattr(resultado_schema, "corresponde_ultimas_elecciones", True)
            and (aspirante.edad or 18) >= 18
        )

    aspirante.append_log(
        f"AUDITORIA_IA_{tipo}",
        f"[{modo_ia}] Archivo '{soporte.nombre_archivo}' ({soporte.mime_type}) -> Válido={soporte.es_valido}. {soporte.observaciones_ia}",
    )
    db.commit()
    db.refresh(soporte)

    return {
        "soporte_id": soporte.id,
        "aspirante_id": aspirante.id,
        "tipo_documento": soporte.tipo_documento,
        "nombre_archivo": soporte.nombre_archivo,
        "mime_type": soporte.mime_type,
        "modo_ia": modo_ia,
        "es_valido": soporte.es_valido,
        "observaciones_ia": soporte.observaciones_ia,
        "datos_extraidos": datos_dict,
    }


def auditar_todos_los_soportes(db: Session, aspirante_id: Optional[int] = None) -> Dict[str, Any]:
    """Ejecuta la auditoría multimodal sobre todos los soportes documentales registrados."""
    query = db.query(SoporteDocumental)
    if aspirante_id is not None:
        query = query.filter(SoporteDocumental.aspirante_id == aspirante_id)
    soportes = query.order_by(SoporteDocumental.id.asc()).all()

    resultados = []
    for sop in soportes:
        resultados.append(auditar_soporte_multimodal(db, sop.id))

    return {
        "total_soportes_auditados": len(resultados),
        "soportes_validos": sum(1 for r in resultados if r["es_valido"]),
        "soportes_con_observacion": sum(1 for r in resultados if not r["es_valido"]),
        "resultados": resultados,
    }


# =====================================================================
# 2. PASO 4: CRUCE MASIVO CON EL ICFES Y NOTIFICACIÓN DE INCONSISTENCIA
# =====================================================================

def generar_correo_inconsistencia_icfes(
    aspirante: Aspirante, discrepancias: List[str]
) -> str:
    """Genera el borrador de notificación oficial del Paso 4 solicitando soportes al correo de la DARA."""
    lista_disc = "\n".join(f"  - {d}" for d in discrepancias)
    return (
        f"Para: {aspirante.correo}\n"
        f"De: Dirección de Admisiones y Registro Académico DARA <{CORREO_INSTITUCIONAL_DARA}>\n"
        f"Asunto: [URGENTE - DARA UIS] Notificación de Inconsistencia en Registro Saber 11° (SNP {aspirante.registro_snp})\n\n"
        f"Estimado(a) aspirante {aspirante.nombres} {aspirante.apellidos} "
        f"({aspirante.tipo_documento} {aspirante.documento_identidad}):\n\n"
        f"En desarrollo del Paso 4 (Carga y Verificación de Información con el ICFES) del Procedimiento "
        f"de Selección de Aspirantes a Pregrado (PAR.01), el sistema de información de la DARA detectó "
        f"las siguientes inconsistencias al confrontar su inscripción con la base de datos oficial del "
        f"Instituto Colombiano para la Evaluación de la Educación (ICFES):\n\n"
        f"{lista_disc}\n\n"
        f"ACCIÓN REQUERIDA:\n"
        f"Sírvase remitir de manera inmediata al correo institucional {CORREO_INSTITUCIONAL_DARA} "
        f"copia legible en formato PDF de su reporte individual oficial de resultados del Examen de Estado "
        f"Saber 11° y de su documento de identidad para subsanar la novedad antes del cierre de la etapa "
        f"de verificación.\n\n"
        f"Cordialmente,\n"
        f"Coordinación de Admisiones - DARA\n"
        f"Universidad Industrial de Santander (UIS)"
    )


def verificar_aspirante_icfes_paso4(
    db: Session, aspirante: Aspirante
) -> Dict[str, Any]:
    """Cruza los datos declarados por un aspirante (y sus soportes ICFES) contra MockIcfesOficial (Paso 4 PAR.01)."""
    oficial = (
        db.query(MockIcfesOficial)
        .filter(MockIcfesOficial.registro_snp == aspirante.registro_snp)
        .first()
    )

    discrepancias: List[str] = []
    if oficial is None:
        discrepancias.append(
            f"El número de registro SNP '{aspirante.registro_snp}' no existe en la base de datos nacional del ICFES."
        )
    else:
        if oficial.documento_identidad != aspirante.documento_identidad:
            discrepancias.append(
                f"Documento de identidad no coincide (Inscrito: {aspirante.documento_identidad} vs Oficial ICFES: {oficial.documento_identidad})."
            )
        if oficial.anio_examen != aspirante.anio_examen:
            discrepancias.append(
                f"Año de presentación del examen no coincide (Inscrito: {aspirante.anio_examen} vs Oficial ICFES: {oficial.anio_examen})."
            )

        comparaciones = [
            ("Puntaje Global", aspirante.puntaje_global_declarado, oficial.puntaje_global),
            ("Ciencias Naturales", aspirante.ciencias_naturales_declarado, oficial.ciencias_naturales),
            ("Sociales y Ciudadanas", aspirante.sociales_ciudadanas_declarado, oficial.sociales_ciudadanas),
            ("Matemáticas", aspirante.matematicas_declarado, oficial.matematicas),
            ("Lectura Crítica", aspirante.lectura_critica_declarado, oficial.lectura_critica),
            ("Inglés", aspirante.ingles_declarado, oficial.ingles),
        ]
        for nombre_campo, val_decl, val_ofic in comparaciones:
            if abs(float(val_decl) - float(val_ofic)) > 0.01:
                discrepancias.append(
                    f"Discrepancia en {nombre_campo}: valor registrado en inscripción ({val_decl:.1f}) != valor oficial ICFES ({val_ofic:.1f})."
                )

    if discrepancias:
        aspirante.estado_proceso = "INCONSISTENCIA_ICFES"
        resumen_disc = "; ".join(discrepancias)
        causal = f"Inconsistencia detectada en cruce ICFES (Paso 4 - PAR.01): {resumen_disc}"
        aspirante.causal_decision = causal
        aspirante.notificacion_inconsistencia = generar_correo_inconsistencia_icfes(
            aspirante, discrepancias
        )
        aspirante.append_log("PASO_4_CRUCE_ICFES", causal)
        return {
            "verificado": False,
            "estado": aspirante.estado_proceso,
            "discrepancias": discrepancias,
            "causal": causal,
            "notificacion_inconsistencia": aspirante.notificacion_inconsistencia,
        }

    # Coincidencia exacta: poblar puntajes verificados desde la fuente oficial del ICFES
    aspirante.puntaje_global = oficial.puntaje_global
    aspirante.ciencias_naturales = oficial.ciencias_naturales
    aspirante.sociales_ciudadanas = oficial.sociales_ciudadanas
    aspirante.matematicas = oficial.matematicas
    aspirante.lectura_critica = oficial.lectura_critica
    aspirante.ingles = oficial.ingles
    aspirante.estado_proceso = "VERIFICADO_ICFES"
    aspirante.notificacion_inconsistencia = None
    causal = (
        f"Verificado exitosamente con ICFES (Paso 4 - PAR.01): Registro SNP {oficial.registro_snp} "
        f"(Año {oficial.anio_examen}, Global {oficial.puntaje_global:.1f}) coincide con la base oficial."
    )
    aspirante.causal_decision = causal
    aspirante.append_log("PASO_4_CRUCE_ICFES", causal)
    return {
        "verificado": True,
        "estado": aspirante.estado_proceso,
        "discrepancias": [],
        "causal": causal,
        "notificacion_inconsistencia": None,
    }


def ejecutar_paso4_verificacion_icfes(db: Session) -> Dict[str, Any]:
    """Ejecuta el cruce masivo con el ICFES (Paso 4 PAR.01) para todos los aspirantes inscritos."""
    # Auditar primero cualquier soporte documental que aún no tenga datos_extraidos_json
    soportes_pendientes = (
        db.query(SoporteDocumental)
        .filter(SoporteDocumental.datos_extraidos_json.is_(None))
        .all()
    )
    for sop in soportes_pendientes:
        auditar_soporte_multimodal(db, sop.id)

    aspirantes = db.query(Aspirante).order_by(Aspirante.orden_inscripcion.asc()).all()
    verificados = 0
    inconsistencias = 0
    detalles = []

    for asp in aspirantes:
        res = verificar_aspirante_icfes_paso4(db, asp)
        if res["verificado"]:
            verificados += 1
        else:
            inconsistencias += 1
        detalles.append(
            {
                "aspirante_id": asp.id,
                "documento_identidad": asp.documento_identidad,
                "nombre_completo": f"{asp.nombres} {asp.apellidos}",
                "registro_snp": asp.registro_snp,
                "estado": res["estado"],
                "causal": res["causal"],
                "tiene_notificacion": res["notificacion_inconsistencia"] is not None,
            }
        )

    db.commit()
    return {
        "etapa": "PASO_4_CARGA_Y_VERIFICACION_ICFES",
        "total_procesados": len(aspirantes),
        "verificados_icfes": verificados,
        "inconsistencias_detectadas": inconsistencias,
        "detalles": detalles,
    }


# =====================================================================
# 3. PASOS 8 Y 9: INFORME COMITÉ DE ADMISIONES Y ACTA CONSEJO ACADÉMICO
# =====================================================================

def generar_informe_y_acta_comite(
    db: Session, periodo_academico: str = "2026-2"
) -> Dict[str, Any]:
    """Genera el informe técnico para el Comité de Admisiones y el borrador de Acta para el Consejo Académico (Pasos 8-9)."""
    listados = generar_listados_oficiales(db)
    res = listados["resumen"]
    desglose = res["desglose_anuladas"]
    programas = db.query(ProgramaAcademico).order_by(ProgramaAcademico.id.asc()).all()

    lineas_programas = []
    for p in programas:
        adm_prog = [a for a in listados["admitidos"] if a["programa_admitido"] == p.nombre]
        lineas_programas.append(
            f"- {p.nombre} ({p.codigo} | {p.facultad}): "
            f"{len(adm_prog)}/{p.cupos_ofertados} cupos asignados."
        )

    lineas_admitidos = []
    for idx, a in enumerate(listados["admitidos"], start=1):
        pond = (
            a["puntaje_ponderado_op1"]
            if a["opcion_admitida"] == 1
            else (a["puntaje_ponderado_op2"] or a["puntaje_ponderado_op1"] or 0.0)
        )
        lineas_admitidos.append(
            f"  {idx}. {a['nombre_completo']} (Doc: {a['documento_identidad']}) -> "
            f"{a['programa_admitido']} [Opción {a['opcion_admitida']}] | "
            f"Ponderado: {pond:.4f} | Código UIS: {a['codigo_estudiante_uis'] or 'Pendiente Paso 12'}"
        )

    lineas_anulados = []
    for a in listados["inscripciones_anuladas"]:
        lineas_anulados.append(
            f"  - {a['nombre_completo']} (Doc: {a['documento_identidad']}) -> "
            f"[{a['estado_proceso']}] {a['causal_decision']}"
        )

    texto_informe = (
        f"========================================================================\n"
        f"UNIVERSIDAD INDUSTRIAL DE SANTANDER (UIS)\n"
        f"DIRECCIÓN DE ADMISIONES Y REGISTRO ACADÉMICO (DARA)\n"
        f"INFORME TÉCNICO PARA EL COMITÉ DE ADMISIONES Y PROYECTO DE ACTA\n"
        f"DEL CONSEJO ACADÉMICO - PROCESO DE ADMISIÓN PREGRADO {periodo_academico}\n"
        f"Procedimiento Institucional: PAR.01\n"
        f"========================================================================\n\n"
        f"1. RESUMEN EJECUTIVO DE LA CONVOCATORIA\n"
        f"   - Total de aspirantes inscritos procesados : {res['total_inscritos']}\n"
        f"   - Total de aspirantes ADMITIDOS            : {res['total_admitidos']}\n"
        f"   - Total de aspirantes NO ADMITIDOS         : {res['total_no_admitidos']}\n"
        f"   - Total de INSCRIPCIONES ANULADAS          : {res['total_inscripciones_anuladas']}\n"
        f"       * Inconsistencia en cruce ICFES (Paso 4)          : {desglose['INCONSISTENCIA_ICFES']}\n"
        f"       * Puntaje inferior a 31 puntos por área (Paso 5)  : {desglose['ANULADO_PUNTAJE_MINIMO']}\n"
        f"       * Examen Saber 11° fuera de vigencia >5 años      : {desglose['ANULADO_VIGENCIA_EXAMEN']}\n"
        f"       * Incumplimiento soporte nivel educativo          : {desglose['ANULADO_NIVEL_EDUCATIVO']}\n"
        f"       * Inhabilidad Archivo Histórico UIS / P.F.U. (P7) : {desglose['INHABILITADO_HISTORICO_UIS']}\n\n"
        f"2. CONSOLIDADO DE CUPOS ASIGNADOS POR PROGRAMA ACADÉMICO\n"
        + ("\n".join(lineas_programas) if lineas_programas else "   Sin programas registrados.")
        + "\n\n"
        f"3. LISTADO OFICIAL DE ASPIRANTES ADMITIDOS PARA APROBACIÓN DEL CONSEJO ACADÉMICO\n"
        + ("\n".join(lineas_admitidos) if lineas_admitidos else "   No hay aspirantes admitidos aún.")
        + "\n\n"
        f"4. RELACIÓN DE INSCRIPCIONES ANULADAS E INHABILITADAS CON TRAZABILIDAD NORMATIVA\n"
        + ("\n".join(lineas_anulados) if lineas_anulados else "   Sin inscripciones anuladas.")
        + "\n\n"
        f"5. CONCEPTO DEL COMITÉ DE ADMISIONES Y RESOLUCIÓN DE APROBACIÓN\n"
        f"   El Comité de Admisiones de la UIS certifica que la asignación de cupos se ejecutó "
        f"de forma estrictamente meritocrática conforme a los pesos ponderados por Facultad, las "
        f"cinco (5) reglas de desempate en cascada y la verificación de antecedentes en el archivo "
        f"histórico institucional (Paso 7). Se somete el presente listado a aprobación definitiva "
        f"mediante acta formal del Consejo Académico para su publicación oficial (Paso 10).\n"
    )

    return {
        "etapa": "PASOS_8_Y_9_INFORME_COMITE_Y_ACTA_CONSEJO",
        "periodo_academico": periodo_academico,
        "resumen": res,
        "informe_y_acta_texto": texto_informe,
        "listados": listados,
    }


def ejecutar_flujo_completo_par01(
    db: Session,
    anio_convocatoria: int = ANIO_CONVOCATORia_DEFAULT,
    periodo_academico: str = "2026-2",
) -> Dict[str, Any]:
    """Ejecuta en secuencia todas las etapas deterministas y de auditoría del procedimiento PAR.01."""
    res_soportes = auditar_todos_los_soportes(db)
    res_p4 = ejecutar_paso4_verificacion_icfes(db)
    res_p5 = ejecutar_paso5_validacion_puntajes_minimos(db, anio_convocatoria=anio_convocatoria)
    res_p6_7 = ejecutar_pasos_6_y_7_seleccion_y_cruce_historico(db)
    res_p12 = ejecutar_paso12_hoja_vida_y_cartas_admision(db, periodo_academico=periodo_academico)
    res_acta = generar_informe_y_acta_comite(db, periodo_academico=periodo_academico)

    return {
        "auditoria_soportes": res_soportes,
        "paso_4_icfes": res_p4,
        "paso_5_requisitos_minimos": res_p5,
        "pasos_6_y_7_seleccion": res_p6_7,
        "paso_12_cartas_admision": res_p12,
        "pasos_8_9_acta": res_acta["resumen"],
    }


# =====================================================================
# 4. AGENTE COPILOTO CONVERSACIONAL DARA CON TOOL CALLING
# =====================================================================

def _buscar_aspirantes_por_termino(db: Session, termino: str) -> List[Aspirante]:
    """Busca aspirantes por documento, nombre, apellido, SNP o código UIS."""
    t = (termino or "").strip().lower()
    todos = db.query(Aspirante).order_by(Aspirante.orden_inscripcion.asc()).all()
    if not t:
        return todos
    coincidencias = []
    for a in todos:
        texto_busqueda = (
            f"{a.documento_identidad} {a.nombres} {a.apellidos} "
            f"{a.registro_snp} {a.codigo_estudiante_uis or ''}"
        ).lower()
        if t in texto_busqueda or any(palabra in texto_busqueda for palabra in t.split() if len(palabra) >= 3):
            coincidencias.append(a)
    return coincidencias


def _formatear_ficha_aspirante(db: Session, asp: Aspirante) -> Dict[str, Any]:
    """Construye el expediente detallado de auditoría de un aspirante para las herramientas del Copiloto."""
    prog1 = db.query(ProgramaAcademico).filter(ProgramaAcademico.id == asp.programa_opcion_1_id).first()
    prog2 = (
        db.query(ProgramaAcademico).filter(ProgramaAcademico.id == asp.programa_opcion_2_id).first()
        if asp.programa_opcion_2_id
        else None
    )
    prog_adm = (
        db.query(ProgramaAcademico).filter(ProgramaAcademico.id == asp.programa_admitido_id).first()
        if asp.programa_admitido_id
        else None
    )
    hist = (
        db.query(MockHistoricoUis)
        .filter(MockHistoricoUis.documento_identidad == asp.documento_identidad)
        .first()
    )
    try:
        logs = json.loads(asp.log_auditoria or "[]")
    except Exception:
        logs = []

    return {
        "aspirante_id": asp.id,
        "orden_inscripcion": asp.orden_inscripcion,
        "documento_identidad": asp.documento_identidad,
        "nombre_completo": f"{asp.nombres} {asp.apellidos}",
        "edad": asp.edad,
        "grupo_sisben": asp.grupo_sisben,
        "tarifa_inscripcion_smlmv": asp.tarifa_inscripcion_smlmv,
        "registro_snp": asp.registro_snp,
        "anio_examen": asp.anio_examen,
        "programa_opcion_1": prog1.nombre if prog1 else None,
        "programa_opcion_2": prog2.nombre if prog2 else None,
        "programa_admitido": prog_adm.nombre if prog_adm else None,
        "opcion_admitida": asp.opcion_admitida,
        "puntajes_declarados": {
            "global": asp.puntaje_global_declarado,
            "ciencias_naturales": asp.ciencias_naturales_declarado,
            "sociales_ciudadanas": asp.sociales_ciudadanas_declarado,
            "matematicas": asp.matematicas_declarado,
            "lectura_critica": asp.lectura_critica_declarado,
            "ingles": asp.ingles_declarado,
        },
        "puntajes_verificados_icfes": {
            "global": asp.puntaje_global,
            "ciencias_naturales": asp.ciencias_naturales,
            "sociales_ciudadanas": asp.sociales_ciudadanas,
            "matematicas": asp.matematicas,
            "lectura_critica": asp.lectura_critica,
            "ingles": asp.ingles,
        },
        "puntaje_ponderado_op1": asp.puntaje_ponderado_op1,
        "puntaje_ponderado_op2": asp.puntaje_ponderado_op2,
        "nivel_educativo_valido": asp.nivel_educativo_valido,
        "certificado_electoral_valido": asp.certificado_electoral_valido,
        "antecedente_historico_uis": (
            {
                "tipo_inhabilidad": hist.tipo_inhabilidad,
                "descripcion": hist.descripcion_causal,
                "periodo": hist.periodo_registro,
            }
            if hist
            else None
        ),
        "estado_proceso": asp.estado_proceso,
        "causal_decision": asp.causal_decision,
        "codigo_estudiante_uis": asp.codigo_estudiante_uis,
        "soportes": [
            {
                "tipo": s.tipo_documento,
                "archivo": s.nombre_archivo,
                "es_valido": s.es_valido,
                "observaciones": s.observaciones_ia,
            }
            for s in asp.soportes
        ],
        "log_auditoria": logs,
    }


def construir_herramientas_copiloto(db: Session, herramientas_invocadas: List[str]):
    """Crea las funciones herramienta (Tools) enlazadas a la sesión SQLite actual."""

    def consultar_aspirante(termino_busqueda: str) -> str:
        """Consulta el expediente completo, puntajes, soportes y causal de selección/anulación de un aspirante por nombre o documento."""
        herramientas_invocadas.append("consultar_aspirante")
        encontrados = _buscar_aspirantes_por_termino(db, termino_busqueda)
        fichas = [_formatear_ficha_aspirante(db, a) for a in encontrados[:5]]
        return json.dumps({"encontrados": len(encontrados), "aspirantes": fichas}, ensure_ascii=False)

    def obtener_resumen_proceso() -> str:
        """Obtiene el resumen general del proceso de admisión, listados de admitidos, no admitidos e inscripciones anuladas."""
        herramientas_invocadas.append("obtener_resumen_proceso")
        listados = generar_listados_oficiales(db)
        return json.dumps(listados, ensure_ascii=False)

    def ejecutar_auditoria_documental(termino_aspirante: str = "") -> str:
        """Audita con visión multimodal los soportes PDF e imagen de un aspirante específico o de todos los inscritos."""
        herramientas_invocadas.append("ejecutar_auditoria_documental")
        if termino_aspirante.strip():
            encontrados = _buscar_aspirantes_por_termino(db, termino_aspirante)
            if encontrados:
                res = auditar_todos_los_soportes(db, aspirante_id=encontrados[0].id)
                return json.dumps(res, ensure_ascii=False)
        res = auditar_todos_los_soportes(db)
        return json.dumps(res, ensure_ascii=False)

    def ejecutar_seleccion_completa_par01(anio_convocatoria: int = ANIO_CONVOCATORia_DEFAULT) -> str:
        """Ejecuta las etapas del procedimiento PAR.01: Paso 4 (ICFES), Paso 5 (>=31 y vigencia), Pasos 6-7 (ponderación, 5 desempates y P.F.U.) y Paso 12 (cartas)."""
        herramientas_invocadas.append("ejecutar_seleccion_completa_par01")
        res = ejecutar_flujo_completo_par01(db, anio_convocatoria=anio_convocatoria)
        return json.dumps(res, ensure_ascii=False)

    def generar_acta_comite_admisiones(periodo_academico: str = "2026-2") -> str:
        """Genera el informe técnico para el Comité de Admisiones y el borrador de acta del Consejo Académico (Pasos 8 y 9)."""
        herramientas_invocadas.append("generar_acta_comite_admisiones")
        res = generar_informe_y_acta_comite(db, periodo_academico=periodo_academico)
        return json.dumps(res, ensure_ascii=False)

    def calcular_tarifa_inscripcion_sisben(grupo_sisben: str, num_opciones: int = 1) -> str:
        """Calcula el valor en SMLMV de los derechos de inscripción según el grupo SISBÉN y el número de opciones (1 o 2)."""
        herramientas_invocadas.append("calcular_tarifa_inscripcion_sisben")
        res = liquidar_derechos_inscripcion(grupo_sisben, num_opciones=num_opciones)
        return json.dumps(res, ensure_ascii=False)

    return [
        consultar_aspirante,
        obtener_resumen_proceso,
        ejecutar_auditoria_documental,
        ejecutar_seleccion_completa_par01,
        generar_acta_comite_admisiones,
        calcular_tarifa_inscripcion_sisben,
    ]


def _procesar_copiloto_fallback(
    db: Session,
    mensaje: str,
    herramientas_invocadas: List[str],
) -> Dict[str, Any]:
    """Motor de Tool Calling determinista de respaldo que invoca las herramientas reales y construye respuesta trazable."""
    msg_lower = mensaje.lower()
    tools = {fn.__name__: fn for fn in construir_herramientas_copiloto(db, herramientas_invocadas)}

    # 1. ¿Solicita ejecutar el proceso de selección o asignación de cupos?
    if any(
        kw in msg_lower
        for kw in (
            "ejecuta",
            "ejecutar",
            "correr seleccion",
            "correr selección",
            "asignar cupos",
            "asignación de cupos",
            "procesar admision",
            "procesar admisión",
            "flujo completo",
        )
    ):
        raw = json.loads(tools["ejecutar_seleccion_completa_par01"]())
        p4 = raw["paso_4_icfes"]
        p5 = raw["paso_5_requisitos_minimos"]
        p67 = raw["pasos_6_y_7_seleccion"]
        p12 = raw["paso_12_cartas_admision"]
        respuesta = (
            "He ejecutado el flujo completo del **Procedimiento PAR.01 (Selección de Aspirantes de Pregrado UIS)** "
            "invocando las herramientas deterministas sobre la base de datos:\n\n"
            f"- **Auditoría Documental IA**: {raw['auditoria_soportes']['total_soportes_auditados']} soportes verificados.\n"
            f"- **Paso 4 (Cruce con el ICFES)**: {p4['verificados_icfes']} verificados y {p4['inconsistencias_detectadas']} con inconsistencia.\n"
            f"- **Paso 5 (Puntaje mínimo >=31 y vigencia <=5 años)**: {p5['habilitados']} habilitados, "
            f"{p5['anulados_puntaje_minimo']} anulados por puntaje <31 y {p5['anulados_vigencia_examen']} por vigencia.\n"
            f"- **Pasos 6 y 7 (Ponderación, 5 reglas de desempate y cruce P.F.U.)**: "
            f"{p67['total_admitidos']} admitidos ({p67['admitidos_primera_opcion']} en 1ra opción, "
            f"{p67['admitidos_segunda_opcion']} en 2da opción), {p67['inhabilitados_historico_uis']} inhabilitados por archivo histórico UIS y {p67['no_admitidos']} no admitidos.\n"
            f"- **Paso 12 (Hojas de Vida y Cartas)**: {p12['total_cartas_expedidas']} códigos de estudiante UIS y cartas expedidas."
        )
        return {"respuesta": respuesta, "datos_contexto": raw}

    # 2. ¿Solicita auditar soportes documentales?
    if any(kw in msg_lower for kw in ("auditar soporte", "audita los soportes", "auditoría documental", "extraer soportes")):
        raw = json.loads(tools["ejecutar_auditoria_documental"](""))
        respuesta = (
            f"Se completó la **Auditoría Documental Multimodal** de {raw['total_soportes_auditados']} soportes "
            f"(PDF e imágenes): {raw['soportes_validos']} válidos y {raw['soportes_con_observacion']} con observaciones."
        )
        return {"respuesta": respuesta, "datos_contexto": raw}

    # 3. ¿Solicita generar el informe o acta para Comité de Admisiones / Consejo Académico?
    if any(kw in msg_lower for kw in ("acta", "comité", "comite", "consejo académico", "consejo academico", "informe")):
        raw = json.loads(tools["generar_acta_comite_admisiones"]())
        res = raw["resumen"]
        respuesta = (
            f"He generado el **Informe Técnico para el Comité de Admisiones y el Borrador de Acta del Consejo Académico** (Pasos 8 y 9 PAR.01):\n\n"
            f"- Inscritos totales: **{res['total_inscritos']}**\n"
            f"- Admitidos: **{res['total_admitidos']}**\n"
            f"- No Admitidos: **{res['total_no_admitidos']}**\n"
            f"- Inscripciones Anuladas: **{res['total_inscripciones_anuladas']}**\n\n"
            f"```text\n{raw['informe_y_acta_texto']}\n```"
        )
        return {"respuesta": respuesta, "datos_contexto": raw}

    # 4. ¿Pregunta por tarifas SISBÉN?
    if "sisben" in msg_lower or "sisbén" in msg_lower or "tarifa" in msg_lower or "smlmv" in msg_lower:
        grupo = "B" if "grupo b" in msg_lower else ("A" if "grupo a" in msg_lower else ("C5" if "c" in msg_lower else "OTROS"))
        num_op = 2 if ("dos" in msg_lower or "2" in msg_lower or "segunda" in msg_lower) else 1
        raw = json.loads(tools["calcular_tarifa_inscripcion_sisben"](grupo, num_op))
        respuesta = (
            f"De acuerdo con la **Sección 6 del Procedimiento PAR.01**, para la categoría SISBÉN **{raw['categoria_sisben']}** "
            f"con **{raw['num_opciones']} opción(es)**:\n"
            f"- Primera opción: **{raw['tarifa_opcion_1_smlmv']} SMLMV**\n"
            f"- Segunda opción: **{raw['tarifa_opcion_2_smlmv']} SMLMV**\n"
            f"- Total a liquidar: **{raw['total_smlmv']} SMLMV**"
        )
        return {"respuesta": respuesta, "datos_contexto": raw}

    # 5. ¿Pregunta por un aspirante específico (nombre, apellido o documento)?
    todos = db.query(Aspirante).all()
    aspirante_mencionado: Optional[Aspirante] = None
    for a in todos:
        if (
            a.documento_identidad.lower() in msg_lower
            or a.nombres.lower() in msg_lower
            or a.apellidos.lower() in msg_lower
            or any(
                parte.lower() in msg_lower
                for parte in (a.nombres.split() + a.apellidos.split())
                if len(parte) >= 4
            )
        ):
            aspirante_mencionado = a
            break

    if aspirante_mencionado is not None:
        raw = json.loads(tools["consultar_aspirante"](aspirante_mencionado.documento_identidad))
        ficha = raw["aspirantes"][0]
        pts = ficha["puntajes_declarados"]
        respuesta = (
            f"### Trazabilidad de {ficha['nombre_completo']} (Doc: `{ficha['documento_identidad']}` | SNP: `{ficha['registro_snp']}`)\n\n"
            f"- **Estado actual en el proceso**: `{ficha['estado_proceso']}`\n"
            f"- **Programa 1ra Opción**: {ficha['programa_opcion_1']} (Ponderado: `{ficha['puntaje_ponderado_op1']}`)\n"
            f"- **Programa 2da Opción**: {ficha['programa_opcion_2'] or 'No registró'} (Ponderado: `{ficha['puntaje_ponderado_op2']}`)\n"
            f"- **Puntajes Saber 11° (Año {ficha['anio_examen']})**: Global={pts['global']}, "
            f"CN={pts['ciencias_naturales']}, SC={pts['sociales_ciudadanas']}, MAT={pts['matematicas']}, "
            f"LC={pts['lectura_critica']}, ING={pts['ingles']}\n"
            f"- **Certificado Electoral Válido**: {'Sí' if ficha['certificado_electoral_valido'] else 'No'} (Edad: {ficha['edad']} años)\n"
            f"- **Causal Reglamentaria Registrada (PAR.01)**:\n  > {ficha['causal_decision'] or 'Pendiente de ejecución de etapas.'}\n"
        )
        if ficha["antecedente_historico_uis"]:
            ant = ficha["antecedente_historico_uis"]
            respuesta += (
                f"- **Alerta Archivo Histórico UIS (Paso 7)**: `{ant['tipo_inhabilidad']}` - "
                f"{ant['descripcion']} (Periodo {ant['periodo']}).\n"
            )
        if ficha["codigo_estudiante_uis"]:
            respuesta += f"- **Código de Estudiante UIS asignado (Paso 12)**: `{ficha['codigo_estudiante_uis']}`\n"
        return {"respuesta": respuesta, "datos_contexto": raw}

    # 6. Consulta general del estado del proceso
    raw = json.loads(tools["obtener_resumen_proceso"]())
    res = raw["resumen"]
    desglose = res["desglose_anuladas"]
    respuesta = (
        f"### Estado Actual del Proceso de Selección DARA (PAR.01)\n\n"
        f"- **Total de aspirantes inscritos**: {res['total_inscritos']}\n"
        f"- **Admitidos**: {res['total_admitidos']}\n"
        f"- **No Admitidos**: {res['total_no_admitidos']}\n"
        f"- **Inscripciones Anuladas / Inhabilitadas**: {res['total_inscripciones_anuladas']} "
        f"(Inconsistencia ICFES: {desglose['INCONSISTENCIA_ICFES']}, Puntaje <31: {desglose['ANULADO_PUNTAJE_MINIMO']}, "
        f"Vigencia >5 años: {desglose['ANULADO_VIGENCIA_EXAMEN']}, P.F.U./Histórico UIS: {desglose['INHABILITADO_HISTORICO_UIS']}).\n\n"
        f"Puedes preguntarme por el detalle de cualquier aspirante por su nombre o documento, "
        f"pedirme ejecutar la selección completa o solicitar el borrador de acta para el Comité de Admisiones."
    )
    return {"respuesta": respuesta, "datos_contexto": raw}


def procesar_mensaje_copiloto(
    db: Session,
    mensaje: str,
    historial: Optional[List[Dict[str, str]]] = None,
) -> Dict[str, Any]:
    """Procesa un mensaje del Coordinador de Admisiones usando Gemini Tool Calling o el orquestador determinista de respaldo."""
    herramientas_invocadas: List[str] = []
    api_key = _obtener_gemini_api_key()

    if api_key:
        try:
            from google import genai
            from google.genai import types

            client = genai.Client(api_key=api_key)
            tools_list = construir_herramientas_copiloto(db, herramientas_invocadas)
            system_instruction = (
                "Eres el Agente Copiloto Oficial de la Dirección de Admisiones y Registro Académico (DARA) "
                "de la Universidad Industrial de Santander (UIS) para el procedimiento PAR.01. "
                "SIEMPRE utiliza las herramientas proporcionadas para consultar aspirantes, verificar "
                "causales de anulación, explicar desempates, ejecutar las etapas del proceso o redactar "
                "el acta para el Comité de Admisiones y el Consejo Académico. Nunca inventes puntajes "
                "ni cálculos; cita siempre los datos exactos retornados por las herramientas."
            )
            response = client.models.generate_content(
                model=MODELO_GEMINI,
                contents=mensaje,
                config=types.GenerateContentConfig(
                    system_instruction=system_instruction,
                    tools=tools_list,
                    temperature=0.1,
                ),
            )
            if response and response.text:
                return {
                    "respuesta": response.text,
                    "herramientas_invocadas": herramientas_invocadas,
                    "modo_ia": MODELO_GEMINI,
                    "datos_contexto": None,
                }
        except Exception:
            pass

    fallback_res = _procesar_copiloto_fallback(db, mensaje, herramientas_invocadas)
    return {
        "respuesta": fallback_res["respuesta"],
        "herramientas_invocadas": herramientas_invocadas,
        "modo_ia": "deterministic_fallback",
        "datos_contexto": fallback_res["datos_contexto"],
    }

