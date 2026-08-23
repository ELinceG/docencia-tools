# Arquitectura y operación

## Separación de responsabilidades

`docencia-tools` recibe configuración confiable y observaciones de Git/GitHub, produce un estado JSON y deja la publicación a una capa posterior. Un workflow solo debe preparar Python, instalar dependencias declaradas por el profesor, obtener el PR por REST, ejecutar la herramienta y publicar checks, artefactos o labels.

Cada job de GitHub Actions es autosuficiente. Ningún validador instala paquetes ni presupone que otro job lo hizo. El orden obligatorio es `setup-python → instalar docencia-tools → materializar e instalar dependencias confiables → validar frontera de confianza → ejecutar validación`.

## Frontera de confianza

Son confiables el release inmutable de `docencia-tools`, la configuración obtenida desde `trusted_ref` y las referencias oficiales copiadas desde ese mismo árbol. Son no confiables el checkout de `head_sha`, sus scripts, su configuración y sus archivos de infraestructura.

Los tres identificadores tienen funciones diferentes:

- `trusted_ref` selecciona reglas actuales, configuración y referencias oficiales; para revalidación manual normalmente es `main`.
- `merge_base` es calculado por Git y delimita lo que el alumno cambió realmente, sin atribuirle cambios posteriores de infraestructura en `main`.
- `head_sha` fija exactamente el contenido entregado que se inspecciona y, solo tras validar rutas, puede ejecutarse.

Un cambio del alumno a `.docencia/`, `.github/`, pruebas, dependencias o referencias oficiales produce `error:archivos-extra` y bloquea la ejecución técnica. La herramienta nunca carga configuración desde el checkout del PR.

## Configuración pública

Cada actividad declara zona horaria, base, patrón de rama, archivos obligatorios y permitidos, número de revisores, deadlines, reglas de título/descripcion y validaciones técnicas opcionales. Los deadlines existen una sola vez en YAML; un cron futuro será solamente un reloj y Python decidirá la transición.

Una actividad deshabilitada puede usar `PENDIENTE` para deadlines durante su preparación. Antes de activarla se deben registrar timestamps ISO 8601 y cambiar `enabled` a `true`.

## Configuración privada

La configuración privada admite prórrogas, deadline individual, exenciones independientes de realizar y recibir revisión, grupos y pares incompatibles, restricciones dirigidas, preferencias `avoid` y asignaciones forzadas. Los motivos y la identidad de las excepciones no deben copiarse al estado público ni imprimirse en logs públicos.

Una incompatibilidad es una restricción dura. `avoid` se usa solamente cuando no hay solución sin esa relación. Una asignación forzada que contradice una regla dura termina con diagnóstico de configuración y no crea una asignación parcial silenciosa.

## Protocolo, revisabilidad y ejecución

Errores de rama, título y descripción son `protocol_error` y no vuelven no revisable una entrega completa. Base incorrecta, archivos obligatorios ausentes o pertenencia ambigua sí producen `revision:no-revisable`. Los archivos extra bloquean la ejecución de código no confiable aunque el profesor todavía pueda revisar manualmente la entrega.

Una entrega tardía y completa conserva el hecho histórico `entrega:tarde`, queda fuera de la asignación automática y pasa a `revision:profesor`. No se calcula aún una calificación numérica.

## `first_complete_at`

La hora oficial es la primera observación en la que todos los archivos obligatorios existen. Cada resultado conserva timestamp, SHA y fuente. Un webhook persistido puede proporcionar una observación exacta. La reconstrucción de PR antiguos mediante el historial Git usa la fecha de committer y se marca `approximate: true`, porque Git no registra cuándo se hizo push a GitHub.

La puntualidad es un hecho histórico. Corregir después la rama, el título o la descripción elimina errores actuales, pero no reescribe `entrega:tarde`.

## Revisión y réplica

Solo cuenta una GitHub Pull Request Review del revisor asignado con estado `APPROVED` o `CHANGES_REQUESTED` y evidencia breve de cambios, archivos, pruebas y observaciones. Un comentario normal no sustituye la review.

Después de `APPROVED` basta una respuesta del autor. Después de `CHANGES_REQUESTED` se necesita respuesta y al menos un commit posterior. Una segunda review posterior a los commits de réplica es opcional y registra extra, tanto si aprueba como si vuelve a solicitar cambios. Nunca se hace merge automático.

## Estado y labels

El estado público JSON incluye actividad, alumno, PR, `head_sha`, `merge_base`, `trusted_ref`, `first_complete_at`, deadlines general y aplicado, puntualidad, revisabilidad, errores actuales, hechos históricos, excepción aplicada sin motivo privado, asignación, semilla, review, réplica, commits, segunda review y extra. La información privada permanece en otro archivo y otro repositorio.

Las labels se calculan con `desired_labels`; los `error:*` corregidos desaparecen, los estados incompatibles son exclusivos y los hechos históricos se derivan del estado persistente.

## Tipos de fallo

- `infrastructure_error`: entorno, configuración confiable, credenciales o herramienta; corresponde al profesor o infraestructura.
- `protocol_error`: rama, base, título, descripción o archivos; el mensaje indica qué puede corregir el alumno.
- `implementation_error`: sintaxis o funcionamiento del código entregado.
- `academic_validation_error`: comparación o criterio disciplinar declarado por el profesor.

Un workflow debe conservar el tipo en su resumen. La ausencia de NumPy, PyYAML o cualquier dependencia confiable es `infrastructure_error`, nunca un error del alumno.

## Añadir una actividad o un curso

1. Copiar el ejemplo público al repositorio del curso.
2. Definir rutas, fechas, reglas y checks sin código específico en el workflow.
3. Validar con `docencia-tools validar-config`.
4. Añadir excepciones solo al repositorio privado.
5. Probar la actividad desde un entorno limpio y con un PR sintético.

Para otro curso se reutilizan el mismo release y workflow; cambian la configuración, las referencias oficiales y, si hace falta, un comando técnico declarativo.

## Revalidación manual

El workflow preparado recibe `pr_number`. Descarga por REST los metadatos actuales, usa reglas desde el `trusted_ref` actual y hace checkout del `head_sha` sin agregar commits ni archivos a la rama del alumno. El resultado conserva los tres identificadores auditables.

## Publicación de v0.1.0 y migración

1. Sustituir la versión de desarrollo por `0.1.0`, ejecutar pruebas y hacer commit.
2. Crear un repositorio remoto para `docencia-tools`, revisar que sea accesible desde Actions y hacer push de `main`.
3. Crear el tag anotado `v0.1.0`, hacer push del tag y no apuntar cursos a `main`.
4. En el curso, configurar `DOCENCIA_TOOLS_REPOSITORY=organizacion/docencia-tools`, completar deadlines y habilitar actividades.
5. Cambiar el checkout de la herramienta del workflow preparado a `ref: v0.1.0`, habilitar `pull_request` y ejecutar pruebas sintéticas.
6. Mantener los workflows antiguos durante una ventana de comparación; retirarlos uno por uno solo después de resultados equivalentes y una revalidación manual satisfactoria.

La integración privada cross-repo necesitará un GitHub App o token de mínimo privilegio con lectura del repositorio del profesor. Ese secreto todavía no existe: debe configurarse como secreto de organización o entorno y nunca imprimirse. El MVP no intenta adivinar su nombre ni su valor.
