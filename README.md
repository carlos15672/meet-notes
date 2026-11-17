# meet-notes — Etapas 4 y 5

Aplicación local para transcribir reuniones, generar resúmenes, encontrar tareas personales y guardar notas.

## Inicio en Windows

En esta computadora ya están instaladas las dependencias de Python y del frontend.

1. Cierra las terminales anteriores de Vite y Uvicorn si siguen abiertas.
2. Haz doble clic en **Iniciar-meet-notes.cmd**.
3. El primer inicio prepara la IA local: descarga el motor portable oficial de llama.cpp y Qwen2.5-1.5B-Instruct Q4_K_M (aproximadamente 1.2 GB en total).
4. El instalador comprueba el archivo del modelo con SHA256 y ejecuta una inferencia real de prueba.
5. Si todo pasa, inicia ambos servicios y abre http://127.0.0.1:5173/.

Mantén la ventana del iniciador abierta. Ctrl+C detiene únicamente los servicios iniciados por esa ventana.
No se requieren claves de API. El procesamiento del texto ocurre en esta computadora.

Para preparar solamente el modelo, abre **Instalar-IA.cmd**. Después puedes reintentar el análisis de una reunión guardada.

También puedes ejecutar:

~~~powershell
npm.cmd start
~~~

## Uso

- En Nueva reunión, escribe el nombre exacto con el que te mencionan y selecciona un MP3, WAV, M4A o MP4. De los MP4 se utiliza únicamente la pista de audio; no necesitas convertirlos ni cambiarles la extensión.
- Procesar reunión transcribe el audio y guarda inmediatamente su texto.
- A continuación comienza el análisis con IA; puedes consultar la transcripción mientras termina.
- Resumen reúne temas, acuerdos y conclusiones.
- Mis pendientes muestra las asignaciones identificadas para el nombre indicado. Cada tarea incluye una cita verificable y, cuando es posible, sus tiempos en el audio.
- Las fechas se conservan como se dijeron (por ejemplo, “el viernes”). No se inventa una fecha de calendario.
- Cambia el estado entre Pendiente, En curso y Completado; el estado se guarda al seleccionarlo.
- Escribe una nota y pulsa Guardar nota. Los borradores se conservan al cambiar de sección y se avisa antes de cerrar la página si quedan cambios.
- Historial permite buscar por título, nombre o archivo, y abrir reuniones anteriores.
- Si falla el análisis, la transcripción permanece guardada y puede reintentarse sin volver a cargar el audio.

Las reuniones se guardan en backend/data/reuniones.sqlite3 mediante SQLite. Los resultados se recuperan al reiniciar el backend.
El navegador recuerda el identificador de la reunión seleccionada y el nombre. El audio seleccionado no se guarda permanentemente.
Las transcripciones de la etapa anterior que sólo estaban en memoria deben procesarse nuevamente para guardarlas.

## Instalación en otra computadora

Se requiere Windows de 64 bits, Node.js y Python 3.13.

~~~powershell
py -3.13 -m venv .venv-backend
.\.venv-backend\Scripts\python.exe -m pip install -r backend\requirements.txt
npm.cmd install
npm.cmd start
~~~

Para desarrollo, en terminales separadas:

~~~powershell
npm.cmd run dev
~~~

~~~powershell
.\.venv-backend\Scripts\python.exe -m uvicorn main:app --app-dir backend --host 127.0.0.1 --port 8000 --reload --reload-dir backend
~~~

Documentación de la API: http://127.0.0.1:8000/docs
Estado de SQLite y disponibilidad de IA: http://127.0.0.1:8000/api/estado

## Arquitectura

- Frontend: React, Vite, Tailwind y Lucide.
- Transcripción: faster-whisper, PyAV 18 y audio a 16 kHz. Se adapta el transcriptor de Traductor-Final-main y se aprovechan sus pesos locales si están disponibles.
- Análisis: inferencia real con Qwen GGUF mediante llama-completion de llama.cpp. No hay respuestas de demostración en las funciones de producción.
- Salida de IA: esquema JSON validado por Pydantic.
- Fundamentación: las tareas deben pertenecer al usuario y contener una cita presente en la transcripción. Se rechazan citas inventadas y se eliminan fechas sin apoyo en la cita.
- Transcripciones largas: se analizan por bloques con un solapamiento breve; se combinan las categorías del resumen y se eliminan tareas repetidas.
- Persistencia: SQLite con transacciones, claves foráneas, parámetros SQL y WAL.
- Notas: control de versión para evitar que una pestaña antigua sobrescriba un cambio más reciente.
- Reintentos: clave de operación para evitar duplicar una reunión al repetir su guardado.
- Recuperación: un análisis interrumpido por el reinicio del servidor queda marcado para reintentar.
- El análisis se ejecuta después de responder al navegador; la interfaz consulta el avance sin bloquear la navegación.
- Los archivos de audio temporales se eliminan después de transcribir.

Endpoints principales:

| Método | Ruta | Función |
|---|---|---|
| POST | /api/transcribir | Transcribir audio real |
| POST | /api/reuniones | Guardar una transcripción y sus metadatos |
| GET | /api/reuniones | Historial, búsqueda y paginación |
| GET | /api/reuniones/{id} | Recuperar resultados, tareas y notas |
| POST | /api/reuniones/{id}/analizar | Iniciar o reintentar IA |
| PATCH | /api/reuniones/{id}/pendientes/{task_id} | Guardar nota o estado con versión |

## Configuración opcional

Copia .env.example como .env para usar rutas diferentes de modelo, motor o base de datos.
El esquema inicial funciona sin configurar variables ni credenciales.
TEXT_MODEL_PATH permite un GGUF alternativo compatible con la plantilla ChatML utilizada.
LLAMA_CPP_EXECUTABLE permite elegir llama-completion.exe o una versión compatible de llama-cli.exe.

## Pruebas

~~~powershell
npm.cmd test
npm.cmd run build
npm.cmd run test:backend
~~~

Las pruebas de API se ejecutan contra la aplicación ASGI real y una base SQLite temporal.
El entorno de pruebas sustituye el despacho a hilos por ejecución directa porque esta sesión restringe los sockets del bucle de eventos de Windows.
Las pruebas de persistencia usan una respuesta de IA controlada para aislar el guardado; esto no constituye una prueba de calidad del modelo real.
Las pruebas de transcripción existentes usan un audio real del proyecto anterior.
El instalador incluye una prueba separada de inferencia real que debe terminar con “IA LOCAL LISTA”.

## Diseño e IHM

Se conserva la paleta, las superficies y la navegación aprobadas. Los controles mantienen un tamaño cómodo y foco visible.
Las pestañas admiten flechas, Inicio y Fin; los errores y los estados de guardado se anuncian a lectores de pantalla.
Las tareas muestran primero la acción, responsable, fecha y estado; la evidencia está dentro de un desplegable.
Resumen, transcripción y pendientes permanecen separados para reducir la carga de lectura.
No se exige arrastrar archivos ni usar combinaciones de dos manos para las acciones principales.

## Límites de esta entrega

- Modelo Qwen y motor llama.cpp instalados. Se comprobó con IA real un resumen, dos tareas de Carlos, una fecha explícita y la exclusión de un deseo personal. También se verificó el guardado y recuperación de una nota y su estado en SQLite. El iniciador reutiliza estos archivos sin volver a descargarlos.
- Las pruebas del guardado, las rutas y la compilación pasaron; la nueva interfaz todavía requiere una comprobación visual completa en navegador.
- Un modelo pequeño puede omitir tareas o interpretar mal una conversación; las citas permiten revisar los pendientes contra la transcripción.
- Se admiten archivos de hasta 100 MB y audios de hasta 45 minutos. En CPU, las grabaciones largas pueden tardar varios minutos.
- Esta entrega está orientada a un usuario en su propia computadora; no incorpora cuentas, diarización de hablantes ni publicación en internet.
- La conformidad WCAG y las pruebas de usabilidad con personas todavía no están certificadas.


## Revisión de resultados

Las asignaciones explícitas complementan la extracción del modelo: se reconocen adverbios entre el nombre y la obligación, como «también debe», y encargos con presente y una acción futura coordinada. Las citas se contrastan también con la acción y los objetos de la tarea para descartar descripciones que no respalda la evidencia. Las preguntas, condiciones, negaciones y nombres ambiguos mantienen un tratamiento conservador.

Las próximas reuniones con una fecha u hora explícita aparecen en el resumen sin convertirse en una conclusión o decisión inventada.

En **Transcripción → Revisar texto** puedes corregir palabras y pulsar **Guardar versión y analizar**. Se crea otra reunión, marcada como texto revisado y vinculada a la original. La transcripción anterior, sus notas y sus tareas se conservan en la reunión original. El texto editado se analiza sin atribuirle tiempos que no se verificaron contra el audio.

Whisper puede confundir palabras. Una corrección manual se distingue de la salida automática y no se presenta como una mejora de precisión del motor. No se aplican sustituciones automáticas para hacer coincidir audios con un guion de prueba.

El resumen exige citas literales para cada punto y limita la lista global de temas.
Los acuerdos se muestran con el texto de su evidencia y requieren una aprobación o decisión expresa.
Las conclusiones se aceptan de forma conservadora cuando la conversación las formula como un cierre explícito.
Esto puede omitir decisiones implícitas: la ausencia de puntos no demuestra que no existan.
Los temas incluyen un desplegable con su evidencia en los análisis nuevos.
El sistema avisa cuando el nombre ingresado no aparece en la transcripción.
Los análisis antiguos guardados no se recalculan automáticamente al actualizar el código.
Después de modificar el backend, reinicia el servidor para usar las nuevas reglas.


## Interfaz y accesibilidad

La justificación de los cambios visuales, los textos y las comprobaciones de uso está en [docs/interfaz.md](docs/interfaz.md).


## Si los puertos ya están ocupados

Si aparece WinError 10048 o «Port 5173 is already in use», hay un servicio usando esa dirección. Primero abre http://127.0.0.1:5173/; la aplicación puede estar funcionando en otra ventana.

El iniciador reutiliza servicios que responden, consulta directamente las direcciones locales sin pasar por un proxy y no arranca un segundo servidor en un puerto ocupado. Si un servicio ocupado no responde, muestra el problema sin terminar procesos ajenos. Para reiniciar manualmente, usa Ctrl+C en las ventanas anteriores de meet-notes y vuelve a abrir `Iniciar-meet-notes.cmd`.

Si el código se actualizó y sigue apareciendo un mensaje anterior (por ejemplo, se rechaza MP4), abre **Reiniciar-meet-notes.cmd**. Ese acceso comprueba que el proceso pertenece al entorno de Python de esta carpeta antes de cerrarlo y vuelve a iniciar la aplicación. Una reunión en procesamiento bloquea el reinicio. Si Windows no permite identificar el proceso, el acceso se detiene e indica cómo cerrar la terminal manualmente.

El servidor publica la revisión del código cargado en `/api/estado`. El iniciador compara esa revisión con los archivos actuales y evita reutilizar una instancia anterior como si estuviera actualizada.

Pruebas del iniciador: `.venv-backend/Scripts/python.exe -m unittest discover -s scripts/tests -v`.


## Funciones completadas en esta actualización

- Notas con guardado automático después de 800 ms sin escribir; cola por tarea para serializar nota y estado, borradores locales recuperables y revisión explícita de conflictos entre pestañas.
- Resumen general extractivo, formado por citas seleccionadas durante el análisis. Las reuniones antiguas conservan sus notas; se añade una síntesis a partir de citas ya guardadas cuando están disponibles.
- Consolidación conservadora de tareas equivalentes con el mismo objeto y fechas compatibles; conserva todas las citas y evita mezclar acciones distintas. No es un detector universal de paráfrasis.
- «Por confirmar»: propuestas con evidencia literal, confirmación o descarte y elección de nombre cuando se detectan homónimos. Confirmar una propuesta equivalente no borra notas ni estado.
- Cancelación real: trabajos de audio en un proceso propio; al cancelar se detiene ese proceso y sus hijos. El análisis de una transcripción guardada comprueba también una marca de cancelación. Una respuesta antigua no puede sobrescribir un reintento nuevo.
- Los archivos de audio de los trabajos se eliminan al terminar el proceso. Los trabajos interrumpidos se marcan como error al reiniciar el servidor; sus resultados ya guardados permanecen disponibles.

Nuevas rutas: `POST /api/trabajos` (multipart: request_id UUID, userName, title y audio), `GET /api/trabajos/{id}`, `POST /api/trabajos/{id}/cancelar`, `POST /api/reuniones/{id}/cancelar`, `PATCH /api/reuniones/{id}/propuestas/{id}` (version, decision: confirmar/descartar y responsable opcional).

Pruebas: `npm test`; `.venv-backend/Scripts/python.exe -m unittest discover -s backend/tests -v`; `.venv-backend/Scripts/python.exe -u scripts/verify_release.py`.

La validación integral usa una base temporal, una grabación sintética etiquetada y los motores reales. Su transporte ASGI en memoria sustituye únicamente el despacho a hilos, por las restricciones del ejecutor. No equivale a una prueba de usabilidad con personas. La voz sintética inglesa instalada puede producir errores al leer español; la calidad lingüística requiere grabaciones naturales adicionales.

Después de actualizar el código, reinicia el backend para habilitar las rutas nuevas y recarga la página. SQLite se migra añadiendo columnas y tablas, sin borrar reuniones existentes.


## Eliminar reuniones del historial

Cada reunión tiene un botón «Eliminar». Antes del borrado aparece una confirmación con el título y los contenidos que se eliminarán. Se borran de SQLite la reunión, transcripción, resumen, tareas, propuestas y notas; también se retiran sus borradores del navegador y la selección de Resultados si estaba abierta. La acción no se puede deshacer desde la aplicación.

Una reunión en procesamiento debe cancelarse antes. El endpoint `DELETE /api/reuniones/{id}` elimina los datos en una sola transacción; una escritura tardía de notas no puede recrear el registro. Los trabajos terminados conservan únicamente su token anónimo de estado para que una consulta pendiente pueda concluir.
