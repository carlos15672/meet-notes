# Estado del plan maestro de meet-notes

Actualizado el 17 de noviembre de 2026.

## Implementado y comprobado técnicamente

- Carga y transcripción reales; resumen general extractivo, temas, acuerdos y conclusiones.
- Tareas personales con evidencia; consolidación conservadora de acciones equivalentes y sus citas.
- Propuestas por confirmar, elección entre homónimos, confirmación y descarte; conservar notas y estados al consolidar.
- Notas con guardado automático, borradores recuperables y protección ante conflictos entre pestañas.
- Cancelación del proceso propio que transcribe y analiza; cancelación de análisis sobre una transcripción guardada y protección contra respuestas antiguas.
- Persistencia e historial en SQLite; migración que añade tablas y columnas sin borrar datos anteriores.
- Documento de IHM con Gestalt, Fitts, Hick, Jakob y las diez heurísticas de Nielsen.
- Pruebas de API, guardado, cancelación, migración, clasificación y cola de notas. Flujo integral con motores reales y audio sintético en una base temporal.

- Revisión de transcripciones en una versión vinculada; recuperación de obligaciones explícitas y próximas reuniones con evidencia. Piloto revisado con dos tareas; evaluación humana pendiente.

## Pendiente de evaluación humana o más datos

- Pruebas de usabilidad con participantes: tiempos, clics, errores, éxito y satisfacción.
- Recorrido real con lector de pantalla, ampliación de texto y condiciones de uso con una mano. Los chequeos de etiquetas y contraste no certifican WCAG.
- Evaluación lingüística amplia con reuniones naturales y etiquetas de referencia. La muestra sintética comprueba el recorrido técnico; la voz inglesa leyendo español produce errores y no permite atribuir una precisión general al sistema.

La detección de homónimos depende de nombres explícitos en el texto. Si no se puede identificar a quien habla, las referencias de primera persona no se asignan por suposición. La consolidación usa reglas conservadoras y no reconoce cualquier paráfrasis posible.

No se solicita al usuario verificar cada cambio de implementación. Las evaluaciones humanas anteriores se mantienen pendientes de forma explícita.

Captura en vivo, ventana flotante, traducción, cuentas multiusuario y diarización no forman parte de los requisitos obligatorios de esta entrega. El modelo local fue la opción acordada; un proveedor externo por API es una ampliación opcional.
