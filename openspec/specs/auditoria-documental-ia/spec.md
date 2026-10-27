# auditoria-documental-ia Specification

## Purpose

Provee capacidades de extracción multimodal y verificación automática de soportes documentales cargados en formato PDF e imagen por los aspirantes (resultados Saber 11°, diploma o certificado de grado undécimo y certificado electoral), así como el cruce masivo contra los registros oficiales del ICFES y la generación de notificaciones de inconsistencia para la DARA.

## Requirements

### Requirement: Extracción multimodal de soportes documentales en PDF e imagen
El sistema SHALL aceptar soportes de inscripción en formato PDF e imagen (PNG, JPG, WEBP) correspondientes al reporte del Examen de Estado Saber 11°, acta o diploma de bachiller (o certificación de cursar undécimo grado) y certificado electoral, extrayendo de forma estructurada los datos de identificación, fechas y puntajes del documento.

#### Scenario: Extracción exitosa desde soporte Saber 11 en PDF o imagen
- **WHEN** el coordinador de la DARA solicita auditar el soporte del Examen Saber 11° de un aspirante cargado en formato PDF o imagen
- **THEN** el sistema extrae el número de registro SNP, documento de identidad, fecha/año de presentación, puntaje global y los cinco puntajes por área (Ciencias Naturales, Sociales y Ciudadanas, Matemáticas, Lectura Crítica e Inglés) en una estructura de datos validada

#### Scenario: Verificación de soporte de nivel educativo
- **WHEN** el sistema procesa el documento de soporte académico de un aspirante
- **THEN** el sistema determina si corresponde a un acta/diploma de bachiller válido o a una certificación vigente de estar cursando grado undécimo al momento de la inscripción

#### Scenario: Verificación de certificado electoral para desempate
- **WHEN** el sistema analiza el soporte de certificado electoral de un aspirante
- **THEN** el sistema extrae el documento de identidad del titular, verifica que corresponda a las elecciones inmediatamente anteriores a la inscripción y registra si el soporte es válido para aplicar la regla de desempate

### Requirement: Cruce masivo de información con registros del ICFES
El sistema SHALL confrontar los números de registro SNP y las calificaciones declaradas por cada aspirante contra la fuente de datos oficial del ICFES y los soportes extraídos, marcando las inscripciones que presenten discrepancias en puntajes, identidad o año de presentación.

#### Scenario: Coincidencia exacta con los registros del ICFES
- **WHEN** los puntajes por área, el puntaje global y el año de presentación del aspirante coinciden con el registro oficial del ICFES
- **THEN** el sistema marca el estado de verificación ICFES del aspirante como verificado y habilita su paso a la validación de requisitos mínimos

#### Scenario: Detección de inconsistencia y generación de notificación al aspirante
- **WHEN** existe discrepancia entre los puntajes registrados en la inscripción y la base de datos del ICFES o el registro SNP no se encuentra
- **THEN** el sistema marca al aspirante con estado de inconsistencia ICFES y genera el borrador de notificación oficial solicitando la remisión de soportes al correo institucional de la DARA
