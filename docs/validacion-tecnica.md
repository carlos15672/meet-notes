# Comprobaciones técnicas de meet-notes

Fecha: 17 de noviembre de 2026.

## Resultados

- 51 pruebas de backend: rutas, persistencia, migración desde el esquema anterior, datos de IA verificables, revisión de propuestas, homónimos, cancelación, recuperación y errores.
- 29 pruebas de frontend: validación de archivos, contrato de API y cola de notas. Incluyen escritura durante un guardado, nota y estado simultáneos, fallo de red, recuperación de borradores y conflictos entre pestañas.
- 8 pruebas del iniciador: reutilizar servicios y detectar puertos ocupados sin arrancar copias adicionales.
- Compilación de producción realizada con Vite.
- Renderizado de los componentes de resultados con datos de una prueba real. Se comprobaron cuatro campos, sus etiquetas, IDs únicos y referencias ARIA. Esta revisión de HTML no sustituye la lectura con una tecnología de asistencia ni una prueba interactiva completa de navegador.
- Cálculo de contraste para los tres pares documentados en interfaz.md: 16.96:1, 5.17:1 y 4.76:1.

## Pruebas con motores reales

Se ejecutó `scripts/verify_release.py` usando la grabación sintética incluida y una base temporal. La API recibió el audio, un proceso propio ejecutó Whisper y Qwen, los resultados se guardaron en SQLite y una nota y su estado se recuperaron tras abrir conexiones nuevas. La cancelación terminó un proceso de trabajo propio. Los datos de la aplicación del usuario no se usaron para esta prueba.

La muestra dura 30.6 segundos. Usa la voz inglesa Microsoft Zira leyendo español: Whisper produjo errores como «inform» y «de Beria». La prueba verificó el recorrido técnico y una tarea reconocida, no la recuperación perfecta de todas las tareas del guion ni una tasa de precisión general.

Con texto controlado y Qwen real se verificaron tareas de Carlos, una propuesta sin responsable y nombres iguales. Para Carlos Pérez/Carlos López, una confirmación sin elegir identidad fue rechazada; elegir un nombre permitido produjo una tarea confirmada. Las respuestas del modelo no fueron sustituidas por una respuesta preparada en estas inferencias.

Las pruebas unitarias y de rutas también usan dobles de prueba para aislar fallos y comprobar casos concretos. Se distinguen de las ejecuciones reales anteriores. El transporte de API de prueba usa la aplicación ASGI en memoria y reemplaza solo el despacho a hilos, debido a las restricciones del ejecutor.

## Alcance pendiente

No se realizó una evaluación con participantes, no se recogieron tiempos ni satisfacción de personas, ni se certificó WCAG. Falta revisar el recorrido completo con lector de pantalla y condiciones reales de uso con una mano, y medir precisión con grabaciones naturales y etiquetas de referencia. Las reglas conservadoras de nombres y consolidación de tareas no cubren cualquier variación del lenguaje.


## Actualización: eliminación del historial

Se añadieron nueve pruebas de backend y cuatro de frontend para la eliminación. Cubren datos relacionados, aislamiento entre reuniones, bloqueo durante el procesamiento (incluida la transición de transcripción a análisis), reversión completa ante un fallo, guardados tardíos, conteos, CORS y borradores locales. La función se ensayó con bases temporales; no se borraron reuniones reales del usuario.

## Actualización: archivos MP4

El selector, la validación del navegador y las dos rutas de carga aceptan MP4, además de MP3, WAV y M4A. El procesamiento utiliza únicamente el audio. Un MP4 sin pista de audio produce un mensaje específico; siguen vigentes los límites de tamaño y duración.

Se añadieron ocho casos de frontend y seis pruebas de backend. Se generaron contenedores MP4 reales con AAC a partir de la muestra de voz del proyecto anterior: con y sin video, la decodificación recuperó el mismo audio; Whisper reconoció «ganamos» y «partido» en el MP4 con video. También se comprobaron la carga de trabajos, mayúsculas en la extensión, el límite de tamaño, archivos corruptos y video sin sonido. La prueba de carga a trabajos sustituye el inicio del proceso para aislar la recepción del archivo; la transcripción del MP4 se ejecutó con el motor real. No se utilizaron archivos personales de WhatsApp.

## Actualización: servidor anterior después de actualizar

Se reprodujo contra el servidor activo el rechazo 415 de un MP4 vacío, con el mensaje anterior que solo enumera MP3, WAV y M4A. El código actualizado reconoce MP4, pero una instancia ya iniciada conserva las rutas anteriores hasta reiniciarse.

El iniciador ahora compara una revisión SHA256 de los archivos Python del backend con la revisión cargada en el servidor. Una instancia sin revisión o con código diferente muestra una instrucción de reinicio. El nuevo acceso `Reiniciar-meet-notes.cmd` verifica ruta y función del proceso del puerto 8000 y sus ancestros antes de reiniciar la instancia propia; se detiene si hay procesamiento activo o no se puede identificar el proceso. Las pruebas del reinicio sustituyen la consulta de procesos y su terminación; no cerraron procesos del usuario. La sesión de desarrollo no pudo enumerar la instancia activa para reiniciarla directamente.


## Corrección del piloto de validación

Se corrigió el reconocimiento de obligaciones con adverbios entre nombre y verbo, así como encargos con presente y una acción futura coordinada. Una recuperación conservadora con citas literales complementa al modelo. Se contrasta también la acción y el objeto de cada descripción con su cita, para descartar propuestas cuyo texto no respalda la evidencia. La detección de homónimos funciona aunque el nombre se escriba en minúsculas.

Las próximas reuniones con fecha u hora explícita se conservan como información de agenda. La revisión de transcripciones crea una reunión vinculada y marcada como revisión manual; mantiene intactos la transcripción, las tareas y las notas de la versión anterior. No se atribuyen marcas de tiempo al texto editado.

Se probaron cinco variantes de decodificación de voz sobre el piloto. No resolvieron todas las diferencias respecto al guion, por lo que se conservaron los ajustes de Whisper. Las dos correcciones de la copia revisada se hicieron contra el guion; no se presentan como reconocimiento automático corregido ni como una medición de precisión general.

Una primera inferencia de texto sobre el guion revisado produjo JSON inválido. Se simplificó el mensaje de instrucciones del modelo y las siguientes inferencias reales produjeron JSON válido. Con las salidas reales y las reglas finales se recuperaron las dos tareas y la próxima reunión. Las descripciones y sus evidencias se comprobaron por separado.

Resultados finales: 77 pruebas de backend, 49 del frontend y 23 del iniciador correctas; compilación de producción correcta. En navegador se comprobaron entrada a la revisión, foco del editor, bloqueo de guardado sin cambios, protección ante un servidor anterior y cancelación sin cambiar la reunión original. Después de una interrupción del entorno, la comprobación de la copia guardada se hizo por API. Se reinició únicamente la instancia identificada como propia del proyecto y se verificaron su revisión, las dos tareas y la reunión del martes mediante la API activa.

Estas comprobaciones corrigen el piloto; no sustituyen las sesiones de usabilidad con participantes ni una evaluación amplia de precisión lingüística.
