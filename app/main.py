"""Aplicación principal FastAPI para el Agente de Selección de Aspirantes de Pregrado UIS - DARA (PAR.01)."""

from contextlib import asynccontextmanager
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.database import SessionLocal, get_db, init_db
from app.models import Aspirante, ProgramaAcademico, SoporteDocumental
from app.schemas import (
    AspiranteCreate,
    AspiranteOut,
    CopilotChatRequest,
    CopilotChatResponse,
    GeminiConfigRequest,
    ProgramaAcademicoOut,
)
from app.services.ai_agent import (
    MODELO_GEMINI,
    auditar_soporte_multimodal,
    auditar_todos_los_soportes,
    configurar_gemini_runtime,
    ejecutar_flujo_completo_par01,
    ejecutar_paso4_verificacion_icfes,
    ejecutar_paso12_con_ia,
    generar_informe_y_acta_comite,
    limpiar_telemetria_ia,
    obtener_estado_pipeline_par01,
    obtener_modelo_gemini_actual,
    obtener_telemetria_ia,
    probar_conexion_gemini,
    procesar_mensaje_copiloto,
    registrar_evento_motor,
    tiene_gemini_api_key,
)
from app.services.rules_engine import (
    ANIO_CONVOCATORia_DEFAULT,
    ejecutar_paso5_validacion_puntajes_minimos,
    ejecutar_pasos_6_y_7_seleccion_y_cruce_historico,
    generar_listados_oficiales,
    liquidar_derechos_inscripcion,
)
from app.services.seed_data import SEED_DOCS_DIR, poblar_escenario_semilla

UPLOADS_DIR = Path("uploads")
TEMPLATES_DIR = Path("app/templates")

UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
SEED_DOCS_DIR.mkdir(parents=True, exist_ok=True)
TEMPLATES_DIR.mkdir(parents=True, exist_ok=True)

MIME_PERMITIDOS = {
    "application/pdf",
    "image/png",
    "image/jpeg",
    "image/jpg",
    "image/webp",
}


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Inicializa las tablas SQLite y carga el escenario semilla si la base está vacía."""
    init_db()
    db = SessionLocal()
    try:
        if db.query(ProgramaAcademico).count() == 0:
            poblar_escenario_semilla(db)
    finally:
        db.close()
    yield


app = FastAPI(
    title="DARA - UIS | Sistema Agéntico de Selección de Aspirantes (PAR.01)",
    description=(
        "Plataforma híbrida de Auditoría Documental Multimodal IA + Motor Determinista de Reglas "
        "y Copiloto Conversacional para la Dirección de Admisiones y Registro Académico de la UIS."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

app.mount("/seed_docs", StaticFiles(directory=str(SEED_DOCS_DIR)), name="seed_docs")
app.mount("/uploads", StaticFiles(directory=str(UPLOADS_DIR)), name="uploads")
# Recursos de identidad visual institucional UIS (fuente Humanst521, logotipo).
app.mount("/static", StaticFiles(directory="app/static"), name="static")

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


@app.get("/", response_class=HTMLResponse)
def index_dashboard(request: Request):
    """Renderiza el panel principal del Coordinador de Admisiones de la DARA."""
    index_path = TEMPLATES_DIR / "index.html"
    if index_path.exists():
        return templates.TemplateResponse(request, "index.html", {})
    return HTMLResponse(
        content="<h1>DARA - UIS | Sistema de Selección de Aspirantes PAR.01</h1>",
        status_code=200,
    )


@app.get("/api/status")
def api_status(db: Session = Depends(get_db)) -> Dict[str, Any]:
    """Devuelve el estado general del sistema, configuración de IA, telemetría en vivo y estado del pipeline."""
    listados = generar_listados_oficiales(db)
    tiene_key = tiene_gemini_api_key()
    return {
        "status": "ok",
        "procedimiento": "PAR.01 - Selección de Aspirantes a Pregrado UIS",
        "gemini_configurado": tiene_key,
        "modelo_ia": obtener_modelo_gemini_actual() if tiene_key else "deterministic_fallback",
        "telemetria_ia": obtener_telemetria_ia(),
        "pipeline": obtener_estado_pipeline_par01(db),
        "total_programas": db.query(ProgramaAcademico).count(),
        "total_soportes": db.query(SoporteDocumental).count(),
        "resumen": listados["resumen"],
    }


@app.get("/api/config/gemini")
def obtener_config_gemini() -> Dict[str, Any]:
    """Obtiene el estado detallado de configuración del modelo Gemini y su telemetría."""
    return obtener_telemetria_ia()


@app.post("/api/config/gemini")
def actualizar_config_gemini(payload: GeminiConfigRequest) -> Dict[str, Any]:
    """Configura la clave GEMINI_API_KEY y el modelo en vivo, guardándolos en .env y probando la conexión."""
    telemetria = configurar_gemini_runtime(
        api_key=payload.api_key,
        modelo=payload.modelo,
        persistir_env=payload.persistir_env,
    )
    prueba = probar_conexion_gemini() if telemetria["gemini_configurado"] else None
    return {
        "mensaje": "Configuración de Gemini actualizada.",
        "telemetria": obtener_telemetria_ia(),
        "prueba_conexion": prueba,
    }


@app.post("/api/config/gemini/probar")
def endpoint_probar_gemini() -> Dict[str, Any]:
    """Realiza una prueba de conexión en vivo contra Google Gemini API."""
    return probar_conexion_gemini()


@app.post("/api/seed")
def reiniciar_escenario_semilla(db: Session = Depends(get_db)) -> Dict[str, Any]:
    """Reinicia la base de datos con el escenario de demostración y genera los soportes PDF/PNG semilla."""
    limpiar_telemetria_ia()
    res = poblar_escenario_semilla(db)
    return {
        "mensaje": "Escenario semilla de demostración DARA cargado exitosamente.",
        "detalle": res,
    }


@app.get("/api/programas", response_model=List[ProgramaAcademicoOut])
def listar_programas(db: Session = Depends(get_db)):
    """Consulta los programas académicos ofertados con sus pesos porcentuales por Facultad."""
    return db.query(ProgramaAcademico).order_by(ProgramaAcademico.id.asc()).all()


@app.get("/api/aspirantes", response_model=List[AspiranteOut])
def listar_aspirantes(
    estado: Optional[str] = None,
    programa_id: Optional[int] = None,
    db: Session = Depends(get_db),
):
    """Consulta el listado de aspirantes inscritos con sus puntajes, soportes y estado del proceso."""
    query = db.query(Aspirante)
    if estado:
        query = query.filter(Aspirante.estado_proceso == estado)
    if programa_id is not None:
        query = query.filter(
            (Aspirante.programa_opcion_1_id == programa_id)
            | (Aspirante.programa_opcion_2_id == programa_id)
            | (Aspirante.programa_admitido_id == programa_id)
        )
    return query.order_by(Aspirante.orden_inscripcion.asc()).all()


@app.get("/api/aspirantes/{aspirante_id}")
def detalle_aspirante(
    aspirante_id: int, db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """Devuelve el expediente completo de un aspirante incluyendo log de auditoría, soportes y carta."""
    asp = db.query(Aspirante).filter(Aspirante.id == aspirante_id).first()
    if not asp:
        raise HTTPException(status_code=404, detail="Aspirante no encontrado.")

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
    try:
        logs = json.loads(asp.log_auditoria or "[]")
    except Exception:
        logs = []

    out = AspiranteOut.model_validate(asp).model_dump()
    out["programa_opcion_1_nombre"] = prog1.nombre if prog1 else None
    out["programa_opcion_2_nombre"] = prog2.nombre if prog2 else None
    out["programa_admitido_nombre"] = prog_adm.nombre if prog_adm else None
    out["logs_parseados"] = logs
    return out


@app.post("/api/aspirantes", response_model=AspiranteOut, status_code=201)
def crear_aspirante(
    payload: AspiranteCreate, db: Session = Depends(get_db)
):
    """Registra un nuevo aspirante validando el límite reglamentario de máximo 2 opciones y tarifa SISBÉN."""
    try:
        liq = liquidar_derechos_inscripcion(
            payload.grupo_sisben, num_opciones=len(payload.opciones_programas_ids)
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    op1_id = payload.opciones_programas_ids[0]
    op2_id = payload.opciones_programas_ids[1] if len(payload.opciones_programas_ids) == 2 else None

    asp = Aspirante(
        orden_inscripcion=payload.orden_inscripcion,
        tipo_documento=payload.tipo_documento,
        documento_identidad=payload.documento_identidad,
        nombres=payload.nombres,
        apellidos=payload.apellidos,
        correo=payload.correo,
        edad=payload.edad,
        grupo_sisben=payload.grupo_sisben,
        programa_opcion_1_id=op1_id,
        programa_opcion_2_id=op2_id,
        tarifa_inscripcion_smlmv=liq["total_smlmv"],
        registro_snp=payload.registro_snp,
        anio_examen=payload.anio_examen,
        puntaje_global_declarado=payload.puntaje_global_declarado,
        ciencias_naturales_declarado=payload.ciencias_naturales_declarado,
        sociales_ciudadanas_declarado=payload.sociales_ciudadanas_declarado,
        matematicas_declarado=payload.matematicas_declarado,
        lectura_critica_declarado=payload.lectura_critica_declarado,
        ingles_declarado=payload.ingles_declarado,
        nivel_educativo_valido=payload.nivel_educativo_valido,
        certificado_electoral_valido=payload.certificado_electoral_valido,
        estado_proceso="INSCRITO",
        causal_decision="Inscrito en convocatoria pregrado UIS.",
    )
    asp.append_log(
        "PASO_2_INSCRIPCION",
        f"Inscripción creada. Tarifa SISBÉN ({liq['categoria_sisben']}): {liq['total_smlmv']} SMLMV.",
    )
    db.add(asp)
    db.commit()
    db.refresh(asp)
    return asp


@app.post("/api/tarifas/calcular")
def endpoint_calcular_tarifa(
    grupo_sisben: str, num_opciones: int = 1
) -> Dict[str, Any]:
    """Liquida el valor en SMLMV de los derechos de inscripción según clasificación SISBÉN."""
    try:
        res = liquidar_derechos_inscripcion(grupo_sisben, num_opciones=num_opciones)
        registrar_evento_motor(
            etapa="SECCION_6_SISBEN",
            proceso=f"Liquidación determinista tarifa SISBÉN ({grupo_sisben}, {num_opciones} opción/es)",
            uso_llm=False,
            modelo="rules_engine.py",
            resumen=f"Tarifa liquidada: {res['total_smlmv']} SMLMV (Categoría {res['categoria_sisben']}).",
        )
        return res
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/aspirantes/{aspirante_id}/soportes")
async def cargar_soporte_aspirante(
    aspirante_id: int,
    tipo_documento: str = Form(...),
    archivo: UploadFile = File(...),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """Carga un archivo PDF o imagen de soporte para un aspirante y ejecuta su auditoría multimodal IA."""
    asp = db.query(Aspirante).filter(Aspirante.id == aspirante_id).first()
    if not asp:
        raise HTTPException(status_code=404, detail="Aspirante no encontrado.")

    mime = (archivo.content_type or "application/octet-stream").lower()
    if mime not in MIME_PERMITIDOS:
        raise HTTPException(
            status_code=400,
            detail=f"Tipo de archivo '{mime}' no permitido. Use PDF o imagen (PNG, JPG, WEBP).",
        )

    tipo_norm = tipo_documento.strip().upper()
    if tipo_norm not in ("ICFES", "DIPLOMA_BACHILLER", "CERTIFICADO_ELECTORAL"):
        raise HTTPException(
            status_code=400,
            detail="tipo_documento debe ser ICFES, DIPLOMA_BACHILLER o CERTIFICADO_ELECTORAL.",
        )

    nombre_seguro = Path(archivo.filename or f"soporte_{aspirante_id}.pdf").name
    ruta_destino = UPLOADS_DIR / f"asp_{aspirante_id}_{tipo_norm.lower()}_{nombre_seguro}"
    contenido = await archivo.read()
    ruta_destino.write_bytes(contenido)

    sop = SoporteDocumental(
        aspirante_id=asp.id,
        tipo_documento=tipo_norm,
        nombre_archivo=nombre_seguro,
        ruta_archivo=str(ruta_destino),
        mime_type=mime,
    )
    db.add(sop)
    db.commit()
    db.refresh(sop)

    resultado_auditoria = auditar_soporte_multimodal(db, sop.id, usar_llm_directo=True)
    return {
        "mensaje": "Soporte documental cargado y auditado exitosamente.",
        "auditoria": resultado_auditoria,
    }


@app.post("/api/soportes/{soporte_id}/auditar")
def endpoint_auditar_soporte_individual(
    soporte_id: int, db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """Ejecuta la auditoría multimodal IA en vivo sobre un soporte específico ya cargado."""
    try:
        return auditar_soporte_multimodal(db, soporte_id, usar_llm_directo=True)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/api/proceso/auditar-soportes")
def endpoint_auditar_todos_soportes(
    aspirante_id: Optional[int] = None, db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """Audita masivamente todos los soportes documentales en PDF e imagen."""
    return auditar_todos_los_soportes(db, aspirante_id=aspirante_id)


@app.post("/api/proceso/paso4-icfes")
def endpoint_paso4_icfes(db: Session = Depends(get_db)) -> Dict[str, Any]:
    """Ejecuta el Paso 4 (PAR.01): Cruce masivo con el ICFES y generación de notificaciones de inconsistencia."""
    return ejecutar_paso4_verificacion_icfes(db)


@app.post("/api/proceso/paso5-requisitos")
def endpoint_paso5_requisitos(
    anio_convocatoria: int = ANIO_CONVOCATORia_DEFAULT,
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """Ejecuta el Paso 5 (PAR.01): Validación de puntaje mínimo >= 31 por área y vigencia <= 5 años (100% Determinista)."""
    res = ejecutar_paso5_validacion_puntajes_minimos(db, anio_convocatoria=anio_convocatoria)
    registrar_evento_motor(
        etapa="PASO_5_FILTRO_MINIMO",
        proceso="Validación determinista de puntaje >= 31 por área y vigencia <= 5 años (>= 2012)",
        uso_llm=False,
        modelo="rules_engine.py",
        resumen=(
            f"Habilitados={res['habilitados']}, Anulados <31={res['anulados_puntaje_minimo']}, "
            f"Anulados vigencia={res['anulados_vigencia_examen']}."
        ),
    )
    res["uso_llm"] = False
    res["modelo_ia"] = "rules_engine.py"
    res["tipo_motor"] = "DETERMINISTA_PURO"
    return res


@app.post("/api/proceso/pasos6-7-seleccion")
def endpoint_pasos6_y_7_seleccion(
    programa_id: Optional[int] = None, db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """Ejecuta los Pasos 6 y 7 (PAR.01): Ponderación, 5 reglas de desempate, 1ra/2da opción y cruce P.F.U. (100% Determinista)."""
    res = ejecutar_pasos_6_y_7_seleccion_y_cruce_historico(db, programa_id=programa_id)
    registrar_evento_motor(
        etapa="PASOS_6_7_MERITO_PFU",
        proceso="Ponderación por Facultad, 5 desempates en cascada y cruce de inhabilidades P.F.U.",
        uso_llm=False,
        modelo="rules_engine.py",
        resumen=(
            f"Admitidos={res['total_admitidos']} (1ra Op={res['admitidos_primera_opcion']}, "
            f"2da Op={res['admitidos_segunda_opcion']}), P.F.U.={res['inhabilitados_historico_uis']}, "
            f"No admitidos={res['no_admitidos']}."
        ),
    )
    res["uso_llm"] = False
    res["modelo_ia"] = "rules_engine.py"
    res["tipo_motor"] = "DETERMINISTA_PURO"
    return res


@app.get("/api/proceso/listados")
def endpoint_listados_oficiales(
    programa_id: Optional[int] = None, db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """Obtiene los listados oficiales de Admitidos, No Admitidos e Inscripciones Anuladas (Pasos 8 y 10)."""
    return generar_listados_oficiales(db, programa_id=programa_id)


@app.get("/api/proceso/acta-comite")
def endpoint_acta_comite(
    periodo_academico: str = "2026-2", db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """Genera el Informe Técnico para el Comité de Admisiones y el Borrador de Acta del Consejo Académico (Pasos 8 y 9)."""
    return generar_informe_y_acta_comite(db, periodo_academico=periodo_academico)


@app.post("/api/proceso/paso12-cartas")
def endpoint_paso12_cartas(
    periodo_academico: str = "2026-2", db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """Ejecuta el Paso 12 (PAR.01): Asigna código de estudiante UIS, hoja de vida y carta de admisión con apoyo IA."""
    return ejecutar_paso12_con_ia(db, periodo_academico=periodo_academico)


@app.post("/api/proceso/ejecutar-todo")
def endpoint_ejecutar_todo(
    anio_convocatoria: int = ANIO_CONVOCATORia_DEFAULT,
    periodo_academico: str = "2026-2",
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """Ejecuta en un solo paso todo el flujo PAR.01 desde auditoría documental hasta expedición de actas y cartas."""
    return ejecutar_flujo_completo_par01(
        db, anio_convocatoria=anio_convocatoria, periodo_academico=periodo_academico
    )


@app.get("/api/aspirantes/{aspirante_id}/carta")
def obtener_carta_y_documentos_aspirante(
    aspirante_id: int, db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """Devuelve la carta de admisión, hoja de vida académica o notificación de inconsistencia de un aspirante."""
    asp = db.query(Aspirante).filter(Aspirante.id == aspirante_id).first()
    if not asp:
        raise HTTPException(status_code=404, detail="Aspirante no encontrado.")

    return {
        "aspirante_id": asp.id,
        "documento_identidad": asp.documento_identidad,
        "nombre_completo": f"{asp.nombres} {asp.apellidos}",
        "estado_proceso": asp.estado_proceso,
        "codigo_estudiante_uis": asp.codigo_estudiante_uis,
        "hoja_vida_academica": asp.hoja_vida_academica,
        "carta_admision": asp.carta_admision,
        "notificacion_inconsistencia": asp.notificacion_inconsistencia,
    }


@app.post("/api/copilot/chat", response_model=CopilotChatResponse)
def endpoint_copilot_chat(
    payload: CopilotChatRequest, db: Session = Depends(get_db)
):
    """Endpoint conversacional del Agente Copiloto de la DARA con Tool Calling."""
    res = procesar_mensaje_copiloto(
        db=db,
        mensaje=payload.mensaje,
        historial=payload.historial,
    )
    return CopilotChatResponse(**res)
