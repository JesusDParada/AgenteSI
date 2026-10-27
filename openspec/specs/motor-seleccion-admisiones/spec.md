# motor-seleccion-admisiones Specification

## Purpose

Ejecuta de manera determinista las reglas del procedimiento PAR.01 de la UIS para el cálculo de derechos de inscripción por SISBÉN, la validación de puntajes mínimos y vigencia del Examen Saber 11°, la ordenación meritocrática por promedio ponderado para primera y segunda opción, las cinco reglas de desempate en cascada y la verificación de inhabilidades históricas (P.F.U. y sanciones) con reasignación de cupos.

## Requirements

### Requirement: Liquidación de derechos de inscripción según clasificación SISBÉN y opciones
El sistema SHALL calcular el valor de los derechos de inscripción en SMLMV de acuerdo con el grupo socioeconómico SISBÉN del aspirante (Grupo A, Grupo B, C1 a C10, u otro caso) y si inscribe una única opción o primera y segunda opción de programa académico (máximo dos opciones).

#### Scenario: Cálculo de tarifa para primera y segunda opción
- **WHEN** un aspirante clasificado en Grupo B del SISBÉN registra primera y segunda opción de programa académico
- **THEN** el sistema calcula una tarifa de 0,050 SMLMV para la primera opción más 0,0250 SMLMV para la segunda opción (total 0,0750 SMLMV)

#### Scenario: Rechazo de más de dos opciones de programa
- **WHEN** se intenta registrar más de dos programas académicos para un mismo aspirante en un proceso de admisión
- **THEN** el sistema rechaza la operación indicando el límite reglamentario de dos opciones por aspirante

### Requirement: Validación de puntaje mínimo por área y vigencia del Examen Saber 11
El sistema SHALL inhabilitar y anular la inscripción de cualquier aspirante a programa presencial que obtenga menos de 31 puntos en cualquiera de las cinco áreas del Examen Saber 11° (Ciencias Naturales, Sociales y Ciudadanas, Matemáticas, Lectura Crítica o Inglés) o cuyo examen haya sido presentado antes de 2012 o supere la vigencia máxima de 5 años respecto al año de la convocatoria.

#### Scenario: Inhabilitación por puntaje inferior a 31 puntos en un área
- **WHEN** un aspirante tiene puntajes verificados donde al menos un área es menor a 31 puntos (por ejemplo, 29 en Inglés)
- **THEN** el sistema cambia el estado del aspirante a inscripción anulada registrando la causal de incumplimiento de puntaje mínimo por área

#### Scenario: Inhabilitación por vencimiento de vigencia del examen
- **WHEN** un aspirante a un programa presencial presenta un Examen Saber 11° con antigüedad mayor a 5 años respecto al año del proceso de admisión
- **THEN** el sistema anula la inscripción registrando la causal de examen fuera de vigencia reglamentaria

### Requirement: Cálculo de promedio ponderado y ordenación de mérito por programa
El sistema SHALL calcular para cada aspirante habilitado el promedio ponderado del Examen Saber 11° aplicando los pesos porcentuales definidos por la Facultad y el programa académico, ordenando a los aspirantes de forma descendente para asignar los cupos ofertados en primera opción y posteriormente evaluar los cupos remanentes en segunda opción.

#### Scenario: Ordenación y preselección por promedio ponderado en primera opción
- **WHEN** el coordinador ejecuta el proceso de selección para un programa con N cupos disponibles
- **THEN** el sistema calcula el puntaje ponderado exacto de cada aspirante habilitado según los pesos del programa, los ordena descendentemente y preselecciona a los primeros N aspirantes en primera opción

#### Scenario: Asignación en segunda opción sobre cupos disponibles
- **WHEN** un aspirante habilitado no obtiene cupo en su primera opción y el programa registrado como su segunda opción cuenta con cupos disponibles tras asignar su primera opción
- **THEN** el sistema evalúa al aspirante con el promedio ponderado calculado según los pesos del programa de segunda opción

### Requirement: Resolución de empates mediante cinco reglas prioritarias en cascada
El sistema SHALL resolver cualquier empate en el puntaje ponderado final entre dos o más aspirantes aplicando en estricto orden secuencial: (1) mayor Puntaje Global Saber 11°, (2) mayor puntaje en Lectura Crítica, (3) mayor puntaje en Sociales y Ciudadanas, (4) certificado electoral válido de las elecciones inmediatamente anteriores (si tienen edad legal para votar), y (5) menor número de orden consecutivo de inscripción.

#### Scenario: Desempate por Puntaje Global o Lectura Crítica
- **WHEN** dos aspirantes empatan en su promedio ponderado para el último cupo disponible de un programa
- **THEN** el sistema asigna la prioridad al aspirante con mayor Puntaje Global, y si persiste el empate, al de mayor puntaje en Lectura Crítica

#### Scenario: Desempate por certificado electoral validado o consecutivo de inscripción
- **WHEN** dos aspirantes mayores de edad mantienen empate en promedio ponderado, Puntaje Global, Lectura Crítica y Sociales y Ciudadanas
- **THEN** el sistema otorga el cupo a quien posea soporte de certificado electoral validado de la última elección, o en su defecto a quien tenga el menor número consecutivo de inscripción

### Requirement: Cruce de inhabilidades históricas UIS y reasignación automática de cupo
El sistema SHALL confrontar a los aspirantes preseleccionados contra el archivo histórico de hojas de vida de la UIS para detectar sanciones disciplinarias vigentes, pérdida de calidad de estudiante por bajo rendimiento (P.F.U.) o falta de renovación reglamentaria, anulando la inscripción afectada y reasignando el cupo al siguiente aspirante en la lista de mérito.

#### Scenario: Anulación por P.F.U. y corrimiento de lista de mérito
- **WHEN** un aspirante ubicado dentro del cupo de preseleccionados registra antecedente de P.F.U. o sanción vigente en el archivo histórico de la UIS
- **THEN** el sistema anula su inscripción dejando trazabilidad de la causal histórica y asigna automáticamente el cupo liberado al siguiente aspirante elegible en el orden de mérito del programa
