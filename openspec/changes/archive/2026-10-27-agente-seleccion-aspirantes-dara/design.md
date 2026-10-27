# Design

## Context

El proyecto se construye sobre un repositorio limpio en Python (`.venv` con Python 3 y pip disponible) tomando como fuente normativa el documento `Procedimiento Selección de Aspirantes a Pregrado UIS.md` (PAR.01). Para la motivación funcional y el alcance de capacidades véase `proposal.md` y los contratos en `specs/`.

El reto arquitectónico principal en un sistema de selección universitaria asistido por IA es evitar que el modelo de lenguaje (LLM) tome decisiones aritméticas o de ordenación de mérito de forma libre (riesgo de alucinación e inequidad), aprovechando en cambio su capacidad cognitiva para:
1. Extraer y validar información desde documentos no estructurados cargados en **PDF e imágenes** (reporte Saber 11°, diploma/certificado de grado 11°, certificado electoral).
2. Orquestar herramientas deterministas (*Tool Calling*) y explicar con trazabilidad completa cada decisión al Coordinador de Admisiones de la DARA.
3. Redactar los documentos formales del proceso (notificaciones de inconsistencia del Paso 4, informe y borrador de acta del Comité/Consejo Académico de los Pasos 8-9, y cartas de admisión del Paso 12).

## Goals / Non-Goals

**Goals:**
- Arquitectura monolítica modular en **FastAPI** que sirva tanto la API REST como el frontend ligero (plantillas Jinja2 + TailwindCSS CDN + JavaScript/Fetch) y persista todo el estado en **SQLite**.
- Separación estricta entre el **Sub-agente de Visión Documental** (extracción multimodal tipada con esquemas Pydantic), el **Motor Determinista de Reglas PAR.01** (cálculos, ponderaciones, 5 reglas de desempate en cascada y cruce de P.F.U.) y el **Copiloto Conversacional DARA** (*Tool Calling*).
- Modo de respaldo (*Fallback / Mock IA*) para que la aplicación y sus pruebas puedan ejecutarse y demostrarse incluso si en un entorno sin conexión o sin clave `GEMINI_API_KEY` se requiere simular la respuesta multimodal o del agente, manteniendo integración real con `google-genai` (`gemini-2.5-flash`) cuando la API key esté configurada.

**Non-Goals:**
- No se implementarán flujos de selección alternativos fuera del flujo principal presencial por Saber 11° (quedan fuera de alcance el cálculo por notas Pre-UIS de Sedes Regionales, la Fase 2 de aptitud musical de Licenciatura en Música, la excepción de programas virtuales/distancia y los sub-flujos jurídicos de Admisión Especial).
- No se implementará integración con pasarelas reales de pago PSE ni con servicios web productivos externos del ICFES; ambos se representan mediante tablas locales en SQLite (`mock_icfes_oficial`, `mock_historico_uis`).
- No se abarcará el proceso posterior al Paso 12 (perfeccionamiento y legalización de matrícula del Paso 13).

## Decisions

### 1. Arquitectura Híbrida: Agente LLM/VLM (`gemini-2.5-flash`) + Motor Determinista en Python
- **Decisión**: Usar el SDK oficial `google-genai` con el modelo `gemini-2.5-flash` para dos funciones: (a) extracción multimodal directa de bytes de archivos PDF/PNG/JPG usando `response_schema` (Pydantic) y (b) agente conversacional con declaración de herramientas Python (`tools=[...]`). Toda validación de umbrales (`>= 31`), vigencia (`<= 5 años` y `>= 2012`), cálculo de ponderados, desempates en cascada y corrimiento de cupos por P.F.U. se ejecuta en funciones puras de Python sobre SQLite.
- **Racional**: `gemini-2.5-flash` procesa PDFs e imágenes de forma nativa sin requerir binarios del sistema operativo como Tesseract o Poppler, cuenta con capa gratuita en Google AI Studio y ofrece baja latencia para el chat copiloto. Delegar las matemáticas y el ordenamiento a Python garantiza cumplimiento 100% auditable del reglamento UIS.
- **Alternativas consideradas**:
  - *OCR tradicional (Tesseract + PyMuPDF) + LLM de solo texto (Groq/Llama)*: Descartado porque obliga a instalar paquetes nativos en Linux/Windows y el OCR falla frecuentemente con tablas de puntajes del ICFES o certificados electorales fotografiados.
  - *Dejar que el LLM ordene y asigne cupos mediante prompt*: Descartado por riesgo de errores de redondeo, incumplimiento del orden estricto de las 5 reglas de desempate y falta de reproducibilidad.

### 2. Persistencia en SQLite con SQLAlchemy y Trazabilidad por Etapas
- **Decisión**: Utilizar SQLite local (`dara_admisiones.db`) gestionado mediante SQLAlchemy 2.0 (modelos declarativos) con 5 entidades centrales:
  1. `ProgramaAcademico`: Pesos de las 5 áreas (suman 100%), facultad y `cupos_ofertados`.
  2. `Aspirante`: Datos de inscripción, `orden_inscripcion`, `grupo_sisben`, `programa_opcion_1_id`, `programa_opcion_2_id`, `programa_admitido_id`, puntajes declarados, puntajes verificados, `puntaje_ponderado_op1`, `puntaje_ponderado_op2`, `estado_proceso`, `causal_decision`, `codigo_estudiante_uis` y trazabilidad en JSON (`log_auditoria`).
  3. `SoporteDocumental`: Metadatos del archivo subido (`ICFES`, `DIPLOMA_BACHILLER`, `CERTIFICADO_ELECTORAL`), ruta en disco, `datos_extraidos_json`, `es_valido` y `observaciones_ia`.
  4. `MockIcfesOficial`: Tabla de referencia nacional simulada por número de registro SNP y documento.
  5. `MockHistoricoUis`: Tabla de antecedentes académicos/disciplinarios (`PFU`, `SANCION_DISCIPLINARIA`, `FALTA_RENOVACION`).
- **Racional**: SQLite no requiere levantar contenedores de base de datos adicionales, facilita reiniciar el escenario de demostración en un clic y permite inspeccionar toda la trazabilidad desde las herramientas del agente.
- **Alternativas consideradas**:
  - *PostgreSQL en Docker*: Innecesario para el volumen de un prototipo académico y añade fricción de configuración.

### 3. Algoritmo de Asignación de Cupos (1ra y 2da Opción) y Corrimiento por Inhabilidades (Pasos 6 y 7)
- **Decisión**: Ejecutar el motor de selección en una transacción reproducible dividida en sub-fases:
  1. Filtrar únicamente aspirantes con estado `VERIFICADO_ICFES` que superaron el Paso 5 (`>= 31` puntos en cada área y vigencia `<= 5 años`, año `>= 2012`).
  2. Calcular `puntaje_ponderado_op1` y `puntaje_ponderado_op2` redondeados a 4 decimales.
  3. Ordenar los aspirantes de cada programa por la tupla de mérito determinista:
     `(-puntaje_ponderado, -puntaje_global, -lectura_critica, -sociales_ciudadanas, -voto_valido_mayor_edad, orden_inscripcion)`.
  4. **Fase Primera Opción + Paso 7 (P.F.U.)**: Recorrer la lista de mérito de cada programa asignando cupos hasta completar `cupos_ofertados`. Para cada preseleccionado, consultar `MockHistoricoUis`; si presenta `PFU`, `SANCION_DISCIPLINARIA` o `FALTA_RENOVACION` vigente, marcar al aspirante como `INHABILITADO_HISTORICO_UIS` con su causal y continuar con el siguiente en la lista de mérito sin consumir el cupo.
  5. **Fase Segunda Opción**: Para los programas que aún tengan cupos remanentes tras la primera opción, evaluar a los aspirantes habilitados no admitidos en primera opción que inscribieron dicho programa como segunda opción, aplicando la misma tupla de mérito y verificación de inhabilidades históricas.
- **Racional**: Modela fielmente los Pasos 6 y 7 del procedimiento PAR.01 en una única llave de ordenamiento en Python, haciendo que el desempate y el corrimiento de cupo sean instantáneos y explicables paso a paso.

### 4. Estructura de la Aplicación Web FastAPI y Frontend Ligero
- **Decisión**: Organizar el código en `app/`:
  - `app/main.py`: Punto de entrada FastAPI, montaje de archivos estáticos/soportes y rutas web/API.
  - `app/database.py` y `app/models.py`: Configuración SQLite y modelos ORM.
  - `app/schemas.py`: Esquemas Pydantic para API y para `response_schema` de Gemini Vision.
  - `app/services/rules_engine.py`: Implementación pura del motor determinista (SISBÉN, Paso 4, Paso 5, Paso 6, Paso 7, Paso 8-12).
  - `app/services/ai_agent.py`: Cliente `google-genai` para auditoría multimodal de PDFs/imágenes, redacción de actas/notificaciones y Chat Copiloto con *Tool Calling* (incluyendo fallback determinista si no hay API key).
  - `app/services/seed_data.py`: Generador de programas UIS, registros ICFES/Histórico, archivos PDF/imagen de soporte de prueba y aspirantes con todos los casos borde.
  - `app/templates/index.html`: Interfaz tipo *Dashboard + Sidebar Copilot* estilizada con TailwindCSS.

```text
+-----------------------------------------------------------------------+
|                       ESTRUCTURA DE MODULOS (app/)                    |
+-----------------------------------------------------------------------+
|                                                                       |
|  [templates/index.html]  <--- HTTP / JSON --->  [app/main.py]         |
|   (Dashboard + Chat UI)                          (FastAPI Endpoints)  |
|                                                    |            |     |
|                         +--------------------------+            |     |
|                         v                                       v     |
|            [services/ai_agent.py]               [services/rules_engine.py]
|        (Gemini Vision + Copilot Tools) -------> (Reglas Exactas PAR.01)
|                         |                                       |     |
|                         +-------------------+-------------------+     |
|                                             v                         |
|                                     [app/models.py]                   |
|                                   (SQLite + seed_data)                |
+-----------------------------------------------------------------------+
```

## Risks / Trade-offs

- **[Ausencia o límite de cuota de `GEMINI_API_KEY` durante pruebas o sustentación]** → Mitigación: Implementar en `ai_agent.py` un modo híbrido que use `gemini-2.5-flash` cuando `GEMINI_API_KEY` esté configurada en el entorno (o en la UI) y cuente con un extractor/respondedor de respaldo basado en los metadatos e inspección local de los soportes de prueba, de modo que la demostración nunca se bloquee.
- **[Formatos variados de archivos PDF e imagen cargados por el usuario]** → Mitigación: Validar MIME types permitidos (`application/pdf`, `image/png`, `image/jpeg`, `image/webp`) al subir el archivo y generar automáticamente en `seed_data.py` documentos PDF/PNG reales de ejemplo (certificados Saber 11°, diplomas y certificados electorales) para probar el flujo multimodal desde el primer arranque.
- **[Trazabilidad de por qué un aspirante ganó o perdió un desempate o corrimiento de cupo]** → Mitigación: Guardar en el campo `log_auditoria` / `causal_decision` de cada aspirante el detalle exacto del cálculo (puntaje ponderado, criterio de desempate aplicado o antecedente histórico detectado) para que tanto la tabla del dashboard como el Chat Copiloto respondan con precisión.

## Migration Plan

Por tratarse de un sistema nuevo (*greenfield*):
1. Instalar dependencias en el entorno virtual existente `.venv`.
2. Inicializar automáticamente las tablas SQLite y los documentos/datos semilla al arrancar la aplicación FastAPI (o mediante el botón "Reiniciar Escenario Demo" en la interfaz).
3. Ejecutar el servidor con `.venv/bin/uvicorn app.main:app --reload`.
