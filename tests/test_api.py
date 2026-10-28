"""Pruebas de integración de los endpoints FastAPI (app/main.py) con TestClient."""

import io
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app


@pytest.fixture
def client(monkeypatch):
    """Configura un TestClient con base de datos SQLite en memoria aislada."""
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def test_api_seed_programas_y_aspirantes(client):
    """Verifica el reinicio del escenario semilla, el renderizado HTML de GET / y la consulta de programas y aspirantes."""
    r_index = client.get("/")
    assert r_index.status_code == 200
    assert "Sistema Agéntico de Selección de Aspirantes a Pregrado" in r_index.text
    assert "Copiloto Conversacional DARA" in r_index.text

    r_seed = client.post("/api/seed")
    assert r_seed.status_code == 200
    data_seed = r_seed.json()
    assert data_seed["detalle"]["programas_creados"] == 6
    assert data_seed["detalle"]["aspirantes_creados"] == 32
    assert data_seed["detalle"]["aspirantes_base"] == 12
    assert data_seed["detalle"]["aspirantes_simpledocs"] == 20

    r_prog = client.get("/api/programas")
    assert r_prog.status_code == 200
    programas = r_prog.json()
    assert len(programas) == 6

    r_asp = client.get("/api/aspirantes")
    assert r_asp.status_code == 200
    aspirantes = r_asp.json()
    assert len(aspirantes) == 32


def test_api_carga_soporte_pdf_y_flujo_por_etapas_par01(client):
    """Verifica la carga de soportes en PDF/imagen, la ejecución paso a paso de PAR.01, actas, cartas y Copiloto."""
    client.post("/api/seed")
    aspirantes = client.get("/api/aspirantes").json()
    primer_asp_id = aspirantes[0]["id"]

    # 1. Subir un archivo PDF de soporte a un aspirante
    pdf_bytes = b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog >>\nendobj\n%%EOF"
    r_upload = client.post(
        f"/api/aspirantes/{primer_asp_id}/soportes",
        data={"tipo_documento": "ICFES"},
        files={"archivo": ("reporte_extra_saber11.pdf", io.BytesIO(pdf_bytes), "application/pdf")},
    )
    assert r_upload.status_code == 200
    assert r_upload.json()["auditoria"]["tipo_documento"] == "ICFES"

    # 2. Ejecutar Paso 4 (Verificación ICFES)
    r_p4 = client.post("/api/proceso/paso4-icfes")
    assert r_p4.status_code == 200
    assert r_p4.json()["verificados_icfes"] == 30
    assert r_p4.json()["inconsistencias_detectadas"] == 2

    # 3. Ejecutar Paso 5 (Puntaje mínimo >=31 y vigencia <=5 años)
    r_p5 = client.post("/api/proceso/paso5-requisitos")
    assert r_p5.status_code == 200
    assert r_p5.json()["habilitados"] == 28
    assert r_p5.json()["anulados_puntaje_minimo"] == 1
    assert r_p5.json()["anulados_vigencia_examen"] == 1

    # 4. Ejecutar Pasos 6 y 7 (Ponderación, 5 desempates y cruce histórico P.F.U.)
    r_p67 = client.post("/api/proceso/pasos6-7-seleccion")
    assert r_p67.status_code == 200
    assert r_p67.json()["total_admitidos"] == 22
    assert r_p67.json()["inhabilitados_historico_uis"] == 1
    assert r_p67.json()["no_admitidos"] == 5

    # 5. Consultar listados y acta para el Comité de Admisiones y Consejo Académico (Pasos 8-10)
    r_acta = client.get("/api/proceso/acta-comite")
    assert r_acta.status_code == 200
    assert "CONSEJO ACADÉMICO" in r_acta.json()["informe_y_acta_texto"]

    # 6. Ejecutar Paso 12 (Códigos de estudiante UIS, hojas de vida y cartas de admisión)
    r_p12 = client.post("/api/proceso/paso12-cartas")
    assert r_p12.status_code == 200
    assert r_p12.json()["total_cartas_expedidas"] == 22

    # Consultar carta de admisión del primer aspirante
    r_carta = client.get(f"/api/aspirantes/{primer_asp_id}/carta")
    assert r_carta.status_code == 200
    assert r_carta.json()["codigo_estudiante_uis"] is not None
    assert "CARTA OFICIAL DE ADMISIÓN" in r_carta.json()["carta_admision"]

    # 7. Probar el endpoint del Chat Copiloto DARA (/api/copilot/chat)
    r_chat = client.post(
        "/api/copilot/chat",
        json={"mensaje": "¿Por qué fue inhabilitado Sebastián Morales o cómo se resolvió el empate de Valentina?"},
    )
    assert r_chat.status_code == 200
    assert "consultar_aspirante" in r_chat.json()["herramientas_invocadas"]
    assert "PFU" in r_chat.json()["respuesta"]


def test_end_to_end_flujo_completo_ejecutar_todo_y_casos_borde(client):
    """Valida de extremo a extremo el endpoint /api/proceso/ejecutar-todo y verifica todos los casos borde del lote semilla y simpledocs."""
    client.post("/api/seed")

    r_todo = client.post("/api/proceso/ejecutar-todo")
    assert r_todo.status_code == 200
    res = r_todo.json()

    assert res["auditoria_soportes"]["total_soportes_auditados"] == 69
    assert res["auditoria_soportes"]["soportes_validos"] == 68
    assert res["auditoria_soportes"]["soportes_con_observacion"] == 1
    assert res["paso_4_icfes"]["verificados_icfes"] == 30
    assert res["paso_4_icfes"]["inconsistencias_detectadas"] == 2
    assert res["paso_5_requisitos_minimos"]["habilitados"] == 28
    assert res["pasos_6_y_7_seleccion"]["total_admitidos"] == 22
    assert res["pasos_6_y_7_seleccion"]["admitidos_primera_opcion"] == 16
    assert res["pasos_6_y_7_seleccion"]["admitidos_segunda_opcion"] == 6
    assert res["paso_12_cartas_admision"]["total_cartas_expedidas"] == 22

    aspirantes = {a["documento_identidad"]: a for a in client.get("/api/aspirantes").json()}

    # 1. Camila (1098700001): Admitida en 1ra opción con código UIS y carta
    assert aspirantes["1098700001"]["estado_proceso"] == "ADMITIDO"
    assert aspirantes["1098700001"]["opcion_admitida"] == 1
    assert aspirantes["1098700001"]["codigo_estudiante_uis"] is not None

    # 2. Sebastián (1098700002): Inhabilitado por P.F.U. en Paso 7
    assert aspirantes["1098700002"]["estado_proceso"] == "INHABILITADO_HISTORICO_UIS"
    assert "PFU" in aspirantes["1098700002"]["causal_decision"]

    # 3. Valentina (1098700003): Gana desempate por Certificado Electoral (Regla 4)
    assert aspirantes["1098700003"]["estado_proceso"] == "ADMITIDO"
    assert "Regla 4" in aspirantes["1098700003"]["causal_decision"]

    # 4. Santiago (1098700004): Entra en el 3er cupo de Sistemas por corrimiento tras P.F.U. de Sebastián
    assert aspirantes["1098700004"]["estado_proceso"] == "ADMITIDO"
    assert "corrimiento" in aspirantes["1098700004"]["causal_decision"]

    # 5. Nicolás (1098700005): Admitido en 2da opción (Matemáticas)
    assert aspirantes["1098700005"]["estado_proceso"] == "ADMITIDO"
    assert aspirantes["1098700005"]["opcion_admitida"] == 2

    # 6. Daniela (1098700006): Anulada por puntaje < 31 en Inglés
    assert aspirantes["1098700006"]["estado_proceso"] == "ANULADO_PUNTAJE_MINIMO"

    # 7. Jorge (1098700007): Anulado por vigencia vencida (> 5 años, examen 2018)
    assert aspirantes["1098700007"]["estado_proceso"] == "ANULADO_VIGENCIA_EXAMEN"

    # 8. Andrés (1098700008): Inconsistencia en cruce ICFES con correo de notificación generado
    assert aspirantes["1098700008"]["estado_proceso"] == "INCONSISTENCIA_ICFES"
    assert "admisiones@uis.edu.co" in aspirantes["1098700008"]["notificacion_inconsistencia"]

    # 12. David (1098700012): No admitido por agotamiento de cupos en Medicina
    assert aspirantes["1098700012"]["estado_proceso"] == "NO_ADMITIDO"

    # 13. Simpledocs #01 - Juanita Romero Caicedo (1034520673):
    # Declaró SNP AC202630601849 pero adjuntó '1 AC202637178411.pdf' perteneciente a Mariana Tovar Quintero
    juanita = aspirantes["1034520673"]
    assert juanita["estado_proceso"] == "INCONSISTENCIA_ICFES"
    assert "Mariana Tovar Quintero" in juanita["causal_decision"]
    soporte_icfes_juanita = next(s for s in juanita["soportes"] if s["tipo_documento"] == "ICFES")
    assert soporte_icfes_juanita["es_valido"] is False
    assert "1 AC202637178411.pdf" in soporte_icfes_juanita["nombre_archivo"]

    # 14. Simpledocs #12 - Matias Luengas Vergel (1092945665): Puntaje perfecto 500/500 -> Admitido en 1ra opción (ING-IND)
    matias = aspirantes["1092945665"]
    assert matias["estado_proceso"] == "ADMITIDO"
    assert matias["opcion_admitida"] == 1
    assert matias["puntaje_global"] == 500.0
    assert len(matias["soportes"]) == 2
    assert all(s["es_valido"] for s in matias["soportes"])


def test_api_pipeline_estado_por_etapas_y_telemetria_llm_vs_determinista(client):
    """Verifica que /api/status reporte el estado de cada etapa del pipeline, sus resultados y qué procesos usan LLM vs Determinista."""
    client.post("/api/seed")

    st_ini = client.get("/api/status").json()
    assert "pipeline" in st_ini
    assert "telemetria_ia" in st_ini
    assert st_ini["pipeline"]["etapas_completadas"] == 0
    assert st_ini["pipeline"]["total_etapas"] == 5

    etapas_ini = {e["codigo"]: e for e in st_ini["pipeline"]["etapas"]}
    assert etapas_ini["ETAPA_1"]["naturaleza_motor"] == "CON_LLM"
    assert etapas_ini["PASO_4"]["naturaleza_motor"] == "HIBRIDO"
    assert etapas_ini["PASO_5"]["naturaleza_motor"] == "SIN_LLM"
    assert etapas_ini["PASOS_6_7"]["naturaleza_motor"] == "SIN_LLM"
    assert etapas_ini["PASOS_8_12"]["naturaleza_motor"] == "HIBRIDO"

    # Ejecutar todo el flujo y verificar que las 5 etapas pasen a completadas con sus resultados
    client.post("/api/proceso/ejecutar-todo")
    st_fin = client.get("/api/status").json()
    assert st_fin["pipeline"]["etapas_completadas"] == 5
    assert st_fin["pipeline"]["porcentaje_avance"] == 100
    assert st_fin["pipeline"]["flujo_completo"] is True

    etapas_fin = {e["codigo"]: e for e in st_fin["pipeline"]["etapas"]}
    assert etapas_fin["ETAPA_1"]["completada"] is True
    assert "69/69" in etapas_fin["ETAPA_1"]["resultado_titulo"]
    assert etapas_fin["PASO_4"]["estado"] == "COMPLETADO_CON_ALERTA"
    assert "30 verificados" in etapas_fin["PASO_4"]["resultado_titulo"]
    assert etapas_fin["PASO_5"]["completada"] is True
    assert "28 habilitados" in etapas_fin["PASO_5"]["resultado_titulo"]
    assert etapas_fin["PASOS_6_7"]["completada"] is True
    assert "22 admitidos" in etapas_fin["PASOS_6_7"]["resultado_titulo"]
    assert etapas_fin["PASOS_8_12"]["completada"] is True
    assert "22 códigos UIS" in etapas_fin["PASOS_8_12"]["resultado_titulo"]
    assert st_fin["telemetria_ia"]["procesos_deterministas_ejecutados"] > 0


