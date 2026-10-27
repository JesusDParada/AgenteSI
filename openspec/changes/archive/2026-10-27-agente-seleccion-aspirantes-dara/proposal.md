# Proposal

## Why

El procedimiento **PAR.01 (Selección de Aspirantes a Programas Académicos de Pregrado de la UIS)** exige a la Dirección de Admisiones y Registro Académico (DARA) cruzar grandes volúmenes de registros con el ICFES, verificar soportes documentales en PDF e imagen (resultados Saber 11°, diplomas/certificados de grado 11° y certificados electorales), aplicar reglas estrictas de habilitación, ponderación, desempate y cruce de inhabilidades históricas (P.F.U./sanciones), y sustentar las decisiones ante el Comité de Admisiones y el Consejo Académico. Desarrollar un Agente de IA híbrido (visión multimodal + herramientas deterministas) integrado en una aplicación web ligera permite automatizar la auditoría documental, garantizar cero errores aritméticos en la asignación meritocrática de cupos y dotar al Coordinador de Admisiones de un copiloto conversacional con trazabilidad completa.

## What Changes

- Se crea una aplicación web backend y frontend ligera servida con **FastAPI** y persistencia en **SQLite**, orientada al Coordinador de Admisiones de la DARA para el flujo principal de admisión presencial de pregrado.
- Se incorpora un módulo de **Auditoría Documental Multimodal con IA** capaz de procesar soportes cargados en **PDF e imágenes** (reporte ICFES Saber 11°, acta/diploma de bachiller o certificado de 11°, y certificado electoral), extraer sus campos estructurados y cruzarlos contra los datos inscritos y la base de datos simulada del ICFES (Paso 4).
- Se implementa un **Motor Determinista de Selección y Asignación de Cupos** invocable como herramienta (*Tool*) del agente que ejecuta sin alucinaciones las reglas del procedimiento PAR.01: validación de puntaje mínimo de 31 puntos por área y vigencia de 5 años (>= 2012) (Paso 5), ponderación por Facultad/Programa para primera y segunda opción, desempate en cascada bajo las 5 reglas reglamentarias (Paso 6), y verificación de inhabilidades en el archivo histórico UIS (P.F.U., sanciones vigentes, falta de renovación) con reasignación automática de cupos (Paso 7).
- Se implementa un **Dashboard Operativo + Chat Copiloto DARA** que permite ejecutar cada etapa del proceso, auditar la causal exacta de admisión/anulación de cada aspirante, generar los listados oficiales, borradores de informes/actas para el Comité de Admisiones y Consejo Académico, notificaciones de inconsistencia y cartas de admisión (Pasos 8 al 12), además de precargar un escenario de demostración con casos borde representativos.

## Capabilities

### New Capabilities
- `auditoria-documental-ia`: Extracción estructurada mediante IA multimodal (PDF e imágenes) de soportes de inscripción (Saber 11°, diploma/certificado 11° y certificado electoral), cruce de consistencia contra registros del ICFES y generación de alertas/notificaciones de inconsistencia.
- `motor-seleccion-admisiones`: Motor determinista de reglas de negocio PAR.01 para liquidación de tarifas SISBÉN, filtrado de requisitos mínimos (>=31 puntos y vigencia <=5 años), cálculo de promedios ponderados por programa (1ra y 2da opción), aplicación de las 5 reglas de desempate en cascada y cruce con el archivo histórico UIS (P.F.U./sanciones) con corrimiento de cupos.
- `copiloto-y-portal-dara`: Interfaz web ligera en FastAPI para el Coordinador de la DARA con pipeline visual por etapas, chat copiloto con *Tool Calling* para consultas y ejecución asistida, generación de listados e informes para Comité/Consejo Académico y datos semilla de demostración.

### Modified Capabilities

## Impact

- **Nuevos módulos de código**: Aplicación en Python sobre `.venv` estructurada bajo `app/` (`main.py`, modelos SQLite/SQLAlchemy o SQLModel, motor determinista de reglas PAR.01, cliente de agente/visión con `google-genai` / Gemini, endpoints FastAPI y plantillas HTML/Tailwind/JS).
- **Dependencias**: `fastapi`, `uvicorn`, `sqlalchemy` (o `sqlmodel`), `pydantic`, `python-multipart` (para carga de PDFs e imágenes), `google-genai` (para visión multimodal de PDFs/imágenes y *tool calling* del agente) y `jinja2`.
- **Datos y Almacenamiento**: Base de datos local SQLite (`dara_admisiones.db`) y directorio local de archivos de soporte (`uploads/` y `seed_docs/`) con casos de prueba simulados.
