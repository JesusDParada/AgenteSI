# Sistema Agéntico de Selección de Aspirantes a Pregrado UIS — DARA (Procedimiento PAR.01)

Aplicación web híbrida (**Auditoría Documental Multimodal IA + Motor Determinista de Reglas + Copiloto Conversacional con Tool Calling**) desarrollada en **FastAPI + SQLite + Gemini 2.5 Flash (`google-genai`)** para automatizar y auditar con trazabilidad completa el procedimiento **PAR.01** de la Dirección de Admisiones y Registro Académico (DARA) de la Universidad Industrial de Santander (UIS).

## Características Principales

1. **Auditoría Documental Multimodal (PDF e Imagen)**:
   - Procesa soportes cargados en formato **PDF** e **imagen (`PNG`, `JPG`, `WEBP`)**: reporte individual del Examen de Estado Saber 11° (`ICFES`), acta/diploma de bachiller o certificado de grado 11° (`DIPLOMA_BACHILLER`) y certificado electoral (`CERTIFICADO_ELECTORAL`).
   - Utiliza `gemini-2.5-flash` con esquemas estructurados Pydantic (`response_schema`) y cuenta con modo de respaldo determinista automático cuando no se define `GEMINI_API_KEY`.
2. **Motor Determinista del Procedimiento PAR.01 (`app/services/rules_engine.py`)**:
   - **Sección 6 (Tarifas SISBÉN)**: Liquidación exacta en SMLMV según grupo SISBÉN (`A`, `B`, `C1-C10`, `OTROS`) para primera y segunda opción (máximo 2 programas).
   - **Paso 4 (Cruce Masivo ICFES)**: Confrontación de número de registro SNP y puntajes por área contra la fuente oficial simulada del ICFES (`MockIcfesOficial`) y generación automática del borrador de notificación de inconsistencia hacia `admisiones@uis.edu.co`.
   - **Paso 5 (Requisitos Mínimos)**: Inhabilitación y anulación automática por puntaje `< 31` puntos en cualquiera de las 5 áreas del Examen Saber 11° o por examen fuera de vigencia (`> 5 años` o anterior a `2012`).
   - **Paso 6 (Selección Meritocrática y 5 Reglas de Desempate en Cascada)**: Cálculo del promedio ponderado según los pesos de cada Facultad/Programa (1ra y 2da opción) y resolución determinista de empates por:
     1. Mayor Puntaje Global Saber 11°.
     2. Mayor puntaje en Lectura Crítica.
     3. Mayor puntaje en Sociales y Ciudadanas.
     4. Certificado Electoral válido de las elecciones inmediatamente anteriores (en mayores de edad).
     5. Menor orden consecutivo de inscripción.
   - **Paso 7 (Archivo Histórico UIS — P.F.U. y Sanciones)**: Verificación de preseleccionados contra `MockHistoricoUis` (`PFU`, `SANCION_DISCIPLINARIA`, `FALTA_RENOVACION`) con anulación y **corrimiento automático de cupo** al siguiente aspirante en orden de mérito.
   - **Pasos 8 al 12 (Listados, Actas y Cartas de Admisión)**: Generación de listados oficiales, informe técnico para el Comité de Admisiones, proyecto de acta para el Consejo Académico, asignación de código de estudiante UIS, apertura de hoja de vida académica y expedición de carta de admisión.
3. **Panel Operativo Web + Chat Copiloto DARA (`app/templates/index.html`)**:
   - Pipeline visual por etapas, visor de expedientes y soportes PDF/PNG reales generados en `seed_docs/`, y chat copiloto con invocación de herramientas (*Tool Calling*).

## Requisitos e Instalación

```bash
# 1. Activar el entorno virtual e instalar dependencias
.venv/bin/pip install -r requirements.txt

# 2. (Opcional) Configurar clave de Google Gemini para visión multimodal y agente en vivo
export GEMINI_API_KEY="tu_api_key_de_google_ai_studio"

# 3. Iniciar el servidor web FastAPI
.venv/bin/uvicorn app.main:app --reload
```

Abre `http://127.0.0.1:8000` en el navegador para usar el panel del Coordinador de Admisiones de la DARA.

## Ejecución de Pruebas Automatizadas

```bash
.venv/bin/pytest -v
```
