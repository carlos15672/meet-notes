# Justificación de Interacción Humano-Máquina de meet-notes

## Propósito y usuario de referencia

meet-notes permite consultar una reunión sin tomar apuntes durante toda la conversación. Andrés Morales Rivera, la persona de referencia del proyecto, usa principalmente la mano izquierda por una lesión en el brazo derecho. Para este caso se reducen las acciones simultáneas, se evitan arrastres obligatorios y se colocan los controles junto al contenido que modifican. Estas decisiones son hipótesis de diseño fundamentadas; su eficacia con Andrés o participantes equivalentes todavía requiere una evaluación de uso.

La primera fase procesa grabaciones: nombre y audio → transcripción → resumen y pendientes → notas e historial. La captura en vivo y la ventana flotante pertenecen a una ampliación posterior.

## Color, tipografía y jerarquía

El fondo #F8FAFC y las superficies blancas favorecen una lectura prolongada. El gris #E2E8F0 distingue zonas secundarias. El azul #2563EB identifica la acción principal, la selección y el foco. La guía 60–30–10 organiza esos papeles visuales; no se presenta como una medición exacta de la superficie de cada color. Los mensajes de error y de confirmación incorporan texto, además de color.

La familia del sistema evita descargas de fuentes, mantiene formas familiares y permite ampliar el texto. El tamaño base es de 16 px con interlineado de 1.5; títulos, etiquetas y notas auxiliares tienen pesos y tamaños distintos. El nombre de la reunión encabeza los resultados, seguido de fecha, duración y destinatario de los pendientes. El resumen general precede a temas, acuerdos y conclusiones. Las citas y los fragmentos temporales se muestran bajo demanda.

Las combinaciones verificadas con la fórmula de luminancia relativa son aproximadamente: texto #111827 sobre #F8FAFC, 16.96:1; blanco sobre #2563EB, 5.17:1; #64748B sobre blanco, 4.76:1. W3C establece 4.5:1 para texto normal, con las excepciones descritas en el criterio 1.4.3. Estos cálculos cubren esos pares concretos y no constituyen una auditoría completa de contraste de todos los estados.

## Gestalt: relación con los componentes reales

| Principio | Decisión en meet-notes | Relación con el uso |
| --- | --- | --- |
| Proximidad | La nota, su estado y «Guardar ahora» están dentro de la misma tarea. | Reduce el recorrido para actuar sobre esa tarea. |
| Región común | Cada tarea y cada reunión del historial tienen una tarjeta; las propuestas ambiguas se agrupan en «Por confirmar». | Ayuda a distinguir responsabilidades confirmadas de propuestas. |
| Similitud | Se repiten estilos de campos, botones, tarjetas y mensajes en las distintas vistas. | Permite reconocer acciones conocidas. |
| Continuidad | Formulario y lectura siguen un orden vertical; datos, audio y procesamiento aparecen en secuencia. | Facilita seguir el recorrido sin saltos entre extremos de la pantalla. |
| Figura y fondo | Superficies claras con bordes separan el contenido; la acción principal usa el acento azul. | Dirige la atención sin depender de animaciones decorativas. |

## Fitts, Hick y Jakob

**Fitts.** Los botones principales tienen al menos 48 px de alto y un ancho mínimo de 48 px; los controles de una tarea permanecen juntos. En móvil, la navegación inferior acerca los tres destinos a la zona de interacción. Se evita requerir precisión fina para seleccionar el archivo mediante arrastre. La comodidad real y los recorridos del cursor deben medirse con participantes.

**Hick.** La navegación ofrece tres destinos: Nueva reunión, Resultados e Historial. El primer formulario pide nombre, título opcional y audio. Las opciones avanzadas no interrumpen ese recorrido. La evidencia aparece en desplegables y las decisiones sobre asignaciones dudosas se posponen hasta «Por confirmar».

**Jakob.** Se usan patrones familiares: formulario etiquetado, selector de archivo del sistema, pestañas, búsqueda, tarjetas y selectores de estado. Los botones expresan la acción que realizan. La persona puede reconocer los mecanismos sin aprender una navegación particular del proyecto.

## Diez heurísticas de Nielsen aplicadas

| Heurística | Aplicación y alcance |
| --- | --- |
| 1. Visibilidad del estado | Etapas reales de transcripción y análisis; notas con «Cambios sin guardar», «Guardando», «Guardado» o error. |
| 2. Correspondencia con el mundo real | «Mis pendientes», «Mis notas», «Es mi tarea» y fechas tal como fueron dichas, sin convertirlas en fechas inventadas. |
| 3. Control y libertad | Cancelar un trabajo, cambiar el audio, confirmar o descartar propuestas y editar notas. |
| 4. Consistencia y estándares | Controles equivalentes conservan nombre y aspecto; las pestañas siguen el comportamiento habitual de teclado. |
| 5. Prevención de errores | Validación de archivos, bloqueo de envíos accidentales, confirmación de nombres ambiguos y control de versiones al guardar. |
| 6. Reconocimiento antes que recuerdo | Archivo, reunión y evidencia permanecen consultables junto al resultado correspondiente. |
| 7. Flexibilidad y eficiencia | Mouse o teclado, nombre recordado, guardado automático y acceso directo al historial. |
| 8. Minimalismo | Textos directos, resumen breve, tres destinos principales y detalles secundarios desplegables. |
| 9. Recuperación de errores | Borradores conservados, reintento del análisis sin repetir un audio ya transcrito y revisión explícita de conflictos de notas. |
| 10. Ayuda y documentación | Formatos y límites junto al audio, explicación de «Por confirmar», mensajes junto a la acción y README de instalación. |

La tabla describe mecanismos implementados, no resultados de una prueba de usabilidad. Las heurísticas son criterios para revisar el diseño; no garantizan por sí solas una experiencia satisfactoria.

## Accesibilidad y esfuerzo motor

Se usan etiquetas visibles asociadas a campos, regiones semánticas, un enlace para saltar al contenido y foco visible. Las pestañas admiten flechas, Inicio y Fin; Tab y Mayús+Tab mantienen el recorrido normal del navegador. El contenido se puede operar con pulsaciones individuales y no exige combinaciones de dos manos. Los cambios de guardado usan mensajes de estado y los errores se anuncian como alertas.

En pantallas pequeñas el formulario pasa a una columna y se reserva espacio para que la navegación inferior no tape el contenido. Se respeta la preferencia de movimiento reducido y se mantienen bordes visibles en modos de contraste forzado. El criterio AA 2.5.8 de WCAG 2.2 define un mínimo de 24 × 24 px con excepciones; la decisión del proyecto de usar controles principales mayores busca comodidad adicional y no se presenta como el mínimo normativo.

El objetivo es facilitar la interacción con una mano. No se ha certificado conformidad WCAG, no se ha realizado una sesión con lector de pantalla y no se atribuyen resultados a personas que no hayan participado.

## Plan de evaluación de usabilidad (Sección 29)

Para evaluar que una persona que utiliza únicamente la mano izquierda (caso de referencia: Andrés Morales Rivera) complete las tareas principales con el menor esfuerzo motor y cognitivo, se define el siguiente protocolo de cinco tareas y su línea base de interacción mínima en la interfaz actual:

| Tarea de prueba | Recorrido en la interfaz | Clics mínimos (línea base) | Tiempo meta | Métricas a registrar con participantes |
| --- | --- | --- | --- | --- |
| **Prueba 1:** Cargar el audio de una reunión | Escribir nombre (`#user-name`), pulsar «Seleccionar audio», elegir archivo y pulsar «Procesar reunión». | 3 clics + escritura de nombre | < 30 s (sin contar tiempo de IA) | Tiempo (s), clics realizados, errores de formato/validación, completada (Sí/No). |
| **Prueba 2:** Consultar el resumen | Al concluir el procesamiento, la vista **Resultados** abre directamente en la pestaña **Resumen**. | 0–1 clics | < 15 s | Tiempo (s) para localizar acuerdo/tema principal, clics, completada (Sí/No). |
| **Prueba 3:** Localizar los pendientes personales | Pulsar la pestaña **Mis pendientes** (o usar flecha derecha del teclado desde **Resumen**). | 1 clic (o 1 tecla) | < 10 s | Tiempo (s), clics, errores de navegación, completada (Sí/No). |
| **Prueba 4:** Agregar una nota | Hacer clic en el campo «Mis notas» de la tarea y escribir. El guardado automático se ejecuta a los 800 ms (o 1 clic en «Guardar ahora»). | 1 clic + escritura | < 20 s | Tiempo (s), clics, uso de autoguardado vs. botón manual, completada (Sí/No). |
| **Prueba 5:** Guardar y recuperar la información | Recargar la página o ir a **Historial** → «Abrir reunión» y verificar la nota y el estado en **Mis pendientes**. | 1–2 clics | < 15 s | Tiempo (s), clics, errores, satisfacción general (escala 1–5). |

### Plantilla de registro para sesiones con participantes (uso con mano izquierda)

| Participante | P1: Cargar audio (Tiempo / Clics / Errores) | P2: Resumen (Tiempo / Clics / Errores) | P3: Mis pendientes (Tiempo / Clics / Errores) | P4: Agregar nota (Tiempo / Clics / Errores) | P5: Recuperar (Tiempo / Clics / Errores) | % Tareas completadas | Satisfacción (1–5) y observaciones |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Piloto técnico (autor) | Completada (audio MP4 de voz propia y podcast MP3) | Completada (acuerdos y próxima reunión) | Completada (2 tareas de Carlos con citas) | Completada («incluir los cambios») | Completada (persistida en SQLite) | 100 % | Validado en entorno local; pendiente sesión con usuarios externos. |
| Participante 1 | _Pendiente_ | _Pendiente_ | _Pendiente_ | _Pendiente_ | _Pendiente_ | — | — |
| Participante 2 | _Pendiente_ | _Pendiente_ | _Pendiente_ | _Pendiente_ | _Pendiente_ | — | — |
| Participante 3 | _Pendiente_ | _Pendiente_ | _Pendiente_ | _Pendiente_ | _Pendiente_ | — | — |

## Evaluación que puede automatizarse y evaluación humana pendiente

La revisión de texto conserva la transcripción previa: «Revisar texto» enfoca el editor, «Cancelar revisión» restaura el texto y devuelve el foco al botón, y «Guardar versión y analizar» crea una reunión vinculada. La explicación junto al campo indica qué se conserva. Los textos revisados se distinguen de la salida de Whisper y omiten tiempos no verificados. La próxima reunión aparece como información de agenda, separada de las conclusiones.

Las pruebas técnicas cubren persistencia, conflictos de versiones, recuperación de borradores, cancelación de procesos propios, propuestas por confirmar y datos de IA respaldados por citas. Además de la grabación sintética de regresión, el historial local se probó con tres casos reales: una sesión pública extensa en MP3 (donde un nombre ausente no genera falsos pendientes) y una grabación propia en MP4 con voz en español en su versión automática y su versión revisada.

Las pruebas con participantes externos deberán registrar tiempo, clics, errores, éxito y satisfacción usando la tabla anterior, además de revisar el recorrido completo con lector de pantalla, zoom y condiciones reales de uso con una mano. Esas actividades no se sustituyen por pruebas de código.

## Fuentes de referencia

- W3C, contraste mínimo: https://www.w3.org/WAI/WCAG22/Understanding/contrast-minimum.html
- W3C, tamaño mínimo de objetivos: https://www.w3.org/WAI/WCAG22/Understanding/target-size-minimum.html
- Jakob Nielsen, diez heurísticas: https://www.nngroup.com/articles/ten-usability-heuristics/
