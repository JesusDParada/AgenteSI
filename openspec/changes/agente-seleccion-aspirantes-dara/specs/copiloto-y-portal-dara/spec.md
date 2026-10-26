# Spec Delta

## Purpose

Proporciona al Coordinador de Admisiones de la DARA una interfaz web unificada servida por FastAPI con panel de control por etapas, carga de soportes en PDF e imagen, generación de informes/actas para el Comité de Admisiones y Consejo Académico, expedición de cartas de admisión con código de estudiante y un Copiloto conversacional con invocación de herramientas (*Tool Calling*) para auditar y ejecutar el procedimiento PAR.01.

## ADDED Requirements

### Requirement: Panel web de gestión por etapas y carga de soportes documentales
El sistema SHALL presentar al Coordinador de Admisiones un panel web desde el cual pueda visualizar los programas y aspirantes inscritos, cargar o adjuntar soportes en PDF e imagen para un aspirante, ejecutar las etapas del procedimiento PAR.01 y consultar el estado y la causal detallada de cada inscripción.

#### Scenario: Visualización del estado del proceso y carga de soporte a un aspirante
- **WHEN** el coordinador accede al panel principal y adjunta un archivo PDF o imagen de soporte a un aspirante
- **THEN** el sistema almacena el archivo, lo vincula al registro del aspirante y permite disparar su auditoría multimodal desde la interfaz

#### Scenario: Reinicio o carga de escenario de demostración con casos borde
- **WHEN** el coordinador activa la carga de datos semilla de demostración en el panel
- **THEN** el sistema puebla la base de datos con programas de distintas facultades y un conjunto de aspirantes de prueba que incluyen casos de incumplimiento de puntaje mínimo (<31), examen vencido (>5 años), inconsistencia ICFES, empate resuelto por certificado electoral e inhabilidad por P.F.U.

### Requirement: Copiloto conversacional con invocación de herramientas sobre el proceso DARA
El sistema SHALL incluir un chat copiloto lateral en la interfaz web donde el Coordinador de Admisiones pueda formular consultas o solicitar la ejecución de pasos del procedimiento en lenguaje natural, haciendo que el agente invoque herramientas deterministas sobre la base de datos para responder con trazabilidad exacta.

#### Scenario: Consulta explicativa sobre la causal de anulación o desempate de un aspirante
- **WHEN** el coordinador pregunta en el chat copiloto por qué un aspirante específico fue inhabilitado, anulado o superado en un desempate
- **THEN** el agente consulta los registros de auditoría y del motor de selección de ese aspirante y responde detallando sus puntajes, las reglas aplicadas del procedimiento PAR.01 y la causal exacta registrada

#### Scenario: Ejecución asistida de etapa de selección desde el chat copiloto
- **WHEN** el coordinador solicita al copiloto auditar los soportes de un aspirante o ejecutar la asignación de cupos de un programa académico
- **THEN** el agente ejecuta la herramienta correspondiente, actualiza el estado en la base de datos y resume los resultados obtenidos al coordinador

### Requirement: Generación de listados oficiales, informe para Comité y cartas de admisión
El sistema SHALL generar al cierre de la selección los listados oficiales de admitidos, no admitidos e inscripciones anuladas, redactar el informe ejecutivo y borrador de acta para validación del Comité de Admisiones y aprobación del Consejo Académico, y expedir la hoja de vida con código de estudiante UIS y carta de admisión para cada admitido.

#### Scenario: Generación de informe y borrador de acta para Comité y Consejo Académico
- **WHEN** el coordinador solicita generar la documentación de cierre de un proceso de selección ejecutado
- **THEN** el sistema consolida las cifras de inscritos, admitidos, no admitidos y anulados por causal (puntaje <31, vigencia, inconsistencia ICFES, P.F.U./sanciones) y produce el informe formal listo para revisión del Comité de Admisiones y del Consejo Académico

#### Scenario: Expedición automática de código de estudiante UIS y carta de admisión
- **WHEN** el listado de admitidos queda validado en el sistema
- **THEN** el sistema asigna a cada aspirante admitido un código único de estudiante UIS, registra la apertura de su hoja de vida académica y genera su carta oficial de admisión con las instrucciones de legalización de matrícula
