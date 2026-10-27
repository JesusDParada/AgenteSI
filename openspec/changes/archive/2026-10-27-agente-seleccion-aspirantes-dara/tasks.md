# Tasks

## 1. Configuración del Proyecto, Entorno y Base de Datos SQLite

- [x] 1.1 Crear `requirements.txt` e instalar las dependencias (`fastapi`, `uvicorn`, `sqlalchemy`, `pydantic`, `python-multipart`, `jinja2`, `google-genai`, `pillow`, `reportlab`, `pytest`, `httpx`) en `.venv`, verificando que `.venv/bin/python -c "import fastapi, sqlalchemy, google.genai"` se ejecute sin errores.
- [x] 1.2 Implementar `app/database.py`, `app/models.py` y `app/schemas.py` con las 5 entidades SQLite (`ProgramaAcademico`, `Aspirante`, `SoporteDocumental`, `MockIcfesOficial`, `MockHistoricoUis`) y los esquemas Pydantic de entrada/salida, verificando con una prueba en `tests/test_models.py` la creación de tablas y persistencia básica.

## 2. Motor Determinista de Reglas de Admisión PAR.01 (`motor-seleccion-admisiones`)

- [x] 2.1 Implementar en `app/services/rules_engine.py` la liquidación de tarifas de inscripción por SISBÉN (Grupo A, B, C1-C10, Otros) para primera y segunda opción (máximo 2 opciones) y la validación del Paso 5 (puntaje `>= 31` en las 5 áreas y vigencia `<= 5 años` con año `>= 2012`), verificando mediante pruebas unitarias en `tests/test_rules_engine.py` las causales de anulación.
- [x] 2.2 Implementar en `app/services/rules_engine.py` el cálculo del promedio ponderado por Facultad/Programa (1ra y 2da opción), la ordenación con las 5 reglas de desempate en cascada (Puntaje Global, Lectura Crítica, Sociales, Certificado Electoral validado en mayor de edad y Orden de Inscripción) y el cruce del Paso 7 contra `MockHistoricoUis` (`PFU`, `SANCION_DISCIPLINARIA`, `FALTA_RENOVACION`) con corrimiento automático de cupo, verificando todos los escenarios con `pytest tests/test_rules_engine.py`.
- [x] 2.3 Implementar en `app/services/rules_engine.py` la generación de listados oficiales (Admitidos, No Admitidos, Inscripciones Anuladas), la asignación de código de estudiante UIS, hoja de vida y carta de admisión (Paso 12), verificando su salida mediante pruebas unitarias en `tests/test_rules_engine.py`.

## 3. Auditoría Documental Multimodal IA y Copiloto DARA (`auditoria-documental-ia`)

- [x] 3.1 Implementar en `app/services/ai_agent.py` el extractor multimodal de soportes en PDF e imagen (`ICFES`, `DIPLOMA_BACHILLER`, `CERTIFICADO_ELECTORAL`) usando `google-genai` (`gemini-2.5-flash`) con esquemas Pydantic (`response_schema`) y respaldo local determinista cuando no haya `GEMINI_API_KEY`, más el cruce del Paso 4 contra `MockIcfesOficial` y generación del correo de inconsistencia, verificando su funcionamiento con `pytest tests/test_ai_agent.py`.
- [x] 3.2 Implementar en `app/services/ai_agent.py` el Agente Copiloto de la DARA con declaración de herramientas (*Tool Calling*) conectadas a las funciones de consulta, auditoría documental, ejecución del proceso de selección y redacción del informe/acta para el Comité de Admisiones y Consejo Académico, verificando las respuestas y trazabilidad con `pytest tests/test_ai_agent.py`.

## 4. Escenario Semilla, API FastAPI e Interfaz Web del Coordinador (`copiloto-y-portal-dara`)

- [x] 4.1 Implementar `app/services/seed_data.py` para generar soportes reales de ejemplo en PDF e imagen (PNG) en `seed_docs/` y poblar la base de datos con programas de las 4 facultades UIS y un lote de aspirantes que cubra todos los casos borde (`<31` puntos, vigencia vencida, inconsistencia ICFES, empate resuelto por certificado electoral y corrimiento de cupo por P.F.U.), verificando que la inicialización cree los registros y archivos esperados.
- [x] 4.2 Implementar los endpoints en `app/main.py` para consulta de programas y aspirantes, carga de archivos PDF/imagen de soporte, ejecución por etapas del procedimiento PAR.01, reinicio del escenario semilla, descarga/visualización de actas y cartas de admisión, y endpoint `/api/copilot/chat`, verificando las rutas con `TestClient` en `tests/test_api.py`.
- [x] 4.3 Crear la interfaz web ligera en `app/templates/index.html` (servida por FastAPI con TailwindCSS y JavaScript) con el pipeline de etapas DARA, tabla interactiva de aspirantes con visor de soportes y causales, modal de informes/actas y cartas de admisión, y panel lateral de Chat Copiloto, además de documentar las instrucciones de uso en `README.md`, verificando que `GET /` renderice todos los componentes correctamente.

## 5. Verificación de Integración End-to-End

- [x] 5.1 Ejecutar la suite completa de pruebas (`pytest`) y validar el flujo completo desde la carga del escenario semilla hasta la expedición de actas y cartas de admisión a través de la API de FastAPI sin errores.

## Workflow follow-up

- Archivar el cambio con OpenSpec una vez implementadas y verificadas todas las tareas.
