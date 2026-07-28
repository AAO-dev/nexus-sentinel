# Guion de presentación — Nexus Sentinel

Guion para los dos entregables hablados: el **video** (5 min máx., cámara + diapositivas) y la
**demo en vivo** (5 min, pantalla compartida).

- **Diapositivas:** `Presentacion_Nexus_Sentinel.pptx` (12 slides)
- **Interfaz:** https://nexus-sentinel-iota.vercel.app
- **API:** https://nexus-sentinel-api-2m8a.onrender.com

> **Convención:** el texto en cita `>` es lo que **dices**; las viñetas con **[Acción]** es lo que
> **haces** en pantalla. Los tiempos son acumulados.

---

## ⚠️ Antes de grabar o presentar (crítico)

1. **Despierta el backend 3 minutos antes.** El plan gratuito de Render duerme el servicio tras
   15 min de inactividad y la primera petición tarda hasta 50 segundos. Abre
   https://nexus-sentinel-api-2m8a.onrender.com/health y espera a ver
   `{"status":"ok", ...}`. Si no haces esto, la interfaz aparecerá "conectando…" en cámara.
2. **Deja la interfaz abierta y navegada una vez** (Triage → un usuario → Ejecutivo), para que la
   caché ya tenga los datos y todo cargue instantáneo.
3. **Prueba el asistente una vez** (botón 💬) para confirmar que responde.
4. Cierra pestañas y notificaciones; pon el navegador en pantalla completa (F11).
5. Ten a mano el usuario estrella: **U-0737** — está en la **posición #1** de la cola y **es una
   cuenta realmente comprometida**. Lee la nota siguiente sobre qué día usar para qué.

### 📌 Nota importante sobre el caso U-0737 (léela antes de grabar)

| Dato | Valor | Cómo usarlo |
|---|---|---|
| Posición en la cola | **#1** | Tu titular: lo más riesgoso del periodo es un compromiso real |
| ¿Cuenta comprometida de verdad? | **Sí** | Puedes afirmarlo con seguridad |
| Días en alerta | 7 | Muestra que no fue un pico aislado |
| **Día 23** (riesgo 98) | Mejor **explicación SHAP**: NTLM 16 % vs. 1.7 % personal vs. 1.3 % pares | Úsalo para el panel SHAP |
| **Días 20, 22, 26, 27, 29** | Días con **evento confirmado** del red team (riesgos 17 a 74) | Úsalos si te preguntan por la verdad de terreno |
| Grafo ego (día 23) | 6 destinos nuevos de 64 | **No prometas una explosión de nodos rojos**: son 6. Descríbelo como "seis máquinas que nunca había tocado" |

> **Encuadre honesto y seguro:** «La cuenta número uno de mi cola es una cuenta genuinamente
> comprometida, con siete días en alerta durante el periodo, varios de ellos con actividad de
> ataque confirmada.» Eso es cierto al cien por ciento y es un titular fuerte. Evita decir "este
> día concreto fue el ataque" señalando el día 23.

---

# PARTE 1 — Video (5 minutos)

**Enfoque de la rúbrica: usabilidad.** Por eso casi la mitad del video es la interfaz funcionando,
no diapositivas. Aproximadamente 700 palabras habladas.

### Bloque 1 · El gancho (0:00 – 1:00) — Slides 1 a 4

**[Slide 1 · Portada]**

> Hola, soy Andre Arellano. Les presento **Nexus Sentinel**, un sistema que detecta el uso indebido
> de credenciales legítimas dentro de una red corporativa. Y para explicar por qué esto importa,
> déjenme empezar con un caso real.

**[Slide 2 · Target 2013]**

> En 2013, Target sufrió una de las brechas más costosas de la historia. Los atacantes no explotaron
> ninguna vulnerabilidad sofisticada: **robaron la credencial de un proveedor de aire acondicionado**
> y con esa cuenta legítima se movieron por la red hasta las cajas registradoras. Estuvieron dentro
> tres semanas. El resultado: cuarenta millones de tarjetas comprometidas, setenta millones de
> clientes afectados y más de doscientos millones de dólares en pérdidas.

**[Slide 3 · Anatomía del ataque]**

> Fíjense en la anatomía: credencial robada, movimiento lateral hacia sistemas que esa cuenta nunca
> debió tocar, y tres semanas de invisibilidad. El detalle clave es que **ninguna de esas
> autenticaciones rompió una regla**. Todas eran, técnicamente, válidas.

**[Slide 4 · Las dos fallas]**

> Hubo dos fallas. La primera: el sistema de Target **sí generó alertas**, pero nadie las investigó,
> se ahogaron en un mar de avisos sin priorizar. La segunda: la anomalía no estaba en ningún evento
> individual, sino en el **patrón**. Nexus Sentinel ataca exactamente esas dos fallas.

### Bloque 2 · La tesis y los datos (1:00 – 1:45) — Slides 5 y 6

**[Slide 5 · Tesis]**

> Mi solución parte de una idea: **el modelo no ve eventos, ve desviaciones**. Para cada usuario
> construyo una línea base de comportamiento y mido cuánto se aleja de ella cada día.

**[Slide 6 · Los datos]**

> Y lo hago con datos reales, no sintéticos: registros de autenticación de la red del Laboratorio
> Nacional de Los Álamos. Mil cincuenta y un millones de eventos, doce mil usuarios, y ataques
> reales de un equipo de *red team* como verdad de terreno. El reto es el desbalance: solo un caso
> malicioso por cada doscientos sesenta y cinco. Por eso la exactitud queda descartada como métrica.

### Bloque 3 · Cómo lo resuelvo (1:45 – 2:40) — Slides 7 y 8

**[Slide 7 · Ingeniería de variables]**

> El corazón técnico son cuatro niveles de desviación: qué hizo hoy, qué tan distinto es de su
> propio pasado, qué tan distinto de sus pares, y —el más potente— **qué tan nuevo es su grafo de
> conexiones**. Ese cuarto nivel es justo lo que habría delatado a Target: una credencial de
> mantenimiento tocando cajas registradoras que jamás había visitado.

**[Slide 8 · El modelo]**

> Todo eso alimenta un XGBoost calibrado que produce una **puntuación de riesgo de cero a cien**,
> con un semáforo y, siempre, su explicación. Y aquí es donde quiero mostrarles la herramienta
> funcionando.

### Bloque 4 · La interfaz — EL FOCO (2:40 – 4:15)

> *(Cambia a pantalla compartida del navegador)*

- **[Acción] Abre la vista `/triage`.**

> Esta es la consola del analista. Arriba, los indicadores generales. Y abajo, lo más importante:
> **la cola de triaje ordenada por riesgo**, con el motivo de cada caso en una sola línea. Esto
> resuelve la primera falla de Target: las alertas ya no se pierden, llegan priorizadas.

- **[Acción] Haz clic en la fila de U-0737** (riesgo 98, la primera).

> Al seleccionar el caso más grave, el sistema me muestra la evolución de su riesgo y, sobre todo,
> **por qué** lo señaló. Ninguna puntuación viaja sin su explicación.

- **[Acción] Señala el panel SHAP, en particular la fila "Ratio NTLM".**

> Aquí está la clave de la usabilidad: no me dice solo "NTLM alto". Me dice que **hoy** usó NTLM en
> el dieciséis por ciento de sus autenticaciones, cuando **su propio promedio** es del uno punto
> siete, y **el de sus compañeros de rol**, uno punto tres. Diez veces por encima de lo normal, en
> ambas referencias. Con eso el analista decide en segundos.

- **[Acción] Clic en "Ver investigación completa" (o navega a `/employee/U-0737`).**

> Si necesito profundizar, la vista de investigación me da la actividad del día y este **mini-grafo
> de conexiones**: en gris las máquinas que la cuenta ya conocía, **en rojo las que tocó por primera
> vez**. Aquí veo seis máquinas que esta cuenta jamás había visitado. Ese es el movimiento lateral
> hecho visible: el mismo patrón que en Target pasó desapercibido tres semanas.

- **[Acción] Abre el asistente (botón 💬) y escribe: `¿Por qué se marcó a U-0737?`**

> Y para que la herramienta sea accesible a cualquier usuario, integré un **asistente
> conversacional**. Le pregunto en lenguaje natural y me responde consultando los datos reales del
> modelo, no inventando cifras.

- **[Acción] Mientras responde, cambia a `/executive`.**

> Finalmente, la vista ejecutiva, para el CISO: la tendencia de riesgo por rol de comportamiento y
> la eficiencia del equipo de seguridad.

### Bloque 5 · Valor y cierre (4:15 – 5:00) — Slides 11 y 12

**[Slide 11 · El puente con el negocio]**

> ¿Y cuánto vale esto? El sistema convierte mil millones de eventos en una lista corta. Con un
> presupuesto de **veinte alertas al día**, el equipo cubre el treinta y uno por ciento de las
> cuentas comprometidas; con cien al día, el ochenta y cinco. Esta curva traduce el modelo al
> lenguaje de la dirección: cuántos analistas cuesta cada punto de cobertura.

**[Slide 12 · Cierre]**

> En resumen: **convertimos lo que para Target fue una brecha de más de doscientos millones de
> dólares en una lista corta, priorizada y explicada**. El sistema prioriza y explica; la decisión
> final siempre es de una persona. Gracias.

---

# PARTE 2 — Demo en vivo (5 minutos)

La rúbrica pide: describir **brevemente** el reto y dedicar el resto a la **interfaz**. Regla de
oro: máximo 1 minuto de contexto, 4 minutos de herramienta.

### 0:00 – 0:45 · El reto, en 45 segundos

> Buenas tardes. Mi proyecto es **Nexus Sentinel**: detecta el uso indebido de credenciales
> legítimas, el mismo problema que en 2013 le costó a Target más de doscientos millones de dólares
> cuando robaron la cuenta de un proveedor y se movieron por su red durante tres semanas sin que
> nadie lo notara. El reto técnico es que cada autenticación individual es válida: la señal solo
> existe en el patrón de comportamiento. Trabajé con datos reales de Los Álamos: mil millones de
> eventos y un desbalance de un caso malicioso por cada doscientos sesenta y cinco.

### 0:45 – 2:00 · Vista 1: Triaje (el flujo del analista)

- **[Acción] Muestra `/triage`.**

> Esta es la consola del analista de seguridad. La cola está **ordenada por riesgo**, y cada caso
> trae su motivo en una línea. Aquí ya está resuelto el problema de la fatiga de alertas.

- **[Acción] Clic en U-0737.**

> Selecciono el caso más grave: riesgo noventa y ocho, nivel rojo. El sistema me muestra su
> evolución en el tiempo y la explicación del día que disparó la alerta.

- **[Acción] Recorre el panel SHAP.**

> Y esta comparación triple es el corazón de la usabilidad: el valor de hoy, contra su propio
> histórico, contra sus pares de comportamiento. NTLM al dieciséis por ciento cuando él promedia
> uno punto siete y su grupo uno punto tres.

- **[Acción] Muestra los botones de acción (Falso positivo / Investigar / Escalar).**

> El analista decide y su decisión queda registrada. **Ninguna acción sobre la cuenta es
> automática**: el humano siempre está en el circuito.

### 2:00 – 3:15 · Vista 2: Investigación (el diferenciador)

- **[Acción] Navega a `/employee/U-0737`.**

> Si el caso amerita investigación, aquí tengo la actividad completa del día: cuántas máquinas tocó,
> cuántas eran nuevas, fallos, protocolo y actividad fuera de horario.

- **[Acción] Señala el mini-grafo.**

> Y este es el elemento diferenciador: el **grafo de conexiones**. En gris, las máquinas que la
> cuenta ya conocía; **en rojo, las que tocó por primera vez ese día**. El movimiento lateral, que
> evento por evento era invisible porque cada autenticación era válida, aquí salta a la vista.

> **[Opcional, si quieres un grafo más espectacular]** El usuario **U-1653** (posición 23 de la
> cola, día 20) muestra **33 destinos nuevos de 65** —la mitad de su actividad del día era territorio
> desconocido—. Puedes abrirlo con la URL `…/employee/U-1653?date=20`. Advertencia de honestidad:
> **esa cuenta no está etiquetada como comprometida**, así que si la usas, preséntala como ejemplo
> visual del patrón, no como un acierto del modelo.

### 3:15 – 4:00 · El asistente conversacional

- **[Acción] Abre el asistente y pregunta: `¿Quiénes son los usuarios de mayor riesgo?`**

> Para que la herramienta sea usable por cualquier perfil, integré un asistente conversacional.
> No es un chatbot genérico: cuando necesita un dato, **consulta el modelo real** mediante
> herramientas, así que responde con las cifras verdaderas del periodo.

- **[Acción] Segunda pregunta: `¿Qué significa la puntuación de riesgo?`**

> También sirve de guía: explica los conceptos a alguien que abre la consola por primera vez.

### 4:00 – 4:40 · Vista 3: Ejecutivo (el valor)

- **[Acción] Navega a `/executive`.**

> Y para la dirección, el panel ejecutivo: tendencia de riesgo por rol de comportamiento, las
> cuentas de mayor riesgo sostenido y la eficiencia del equipo.

- **[Acción] Señala los KPIs del SOC.**

> Y quiero destacar algo: aquí reporto la tasa de falsos positivos **sin maquillar**, y el tiempo
> de resolución aparece como "sin datos" porque requiere telemetría real de analistas y **no lo
> inventé**. Prefiero un dato honesto que un número bonito.

### 4:40 – 5:00 · Cierre

> En resumen: Nexus Sentinel toma mil millones de eventos de autenticación y devuelve una lista
> corta, priorizada y explicada, con la decisión final siempre en manos de un analista. Es la
> diferencia entre las alertas que Target ignoró y una cola que un equipo real sí puede atender.
> Muchas gracias.

---

## Preguntas probables y cómo responderlas

| Pregunta | Respuesta corta |
|---|---|
| **¿Por qué el PR-AUC es tan bajo (0.056)?** | Porque el desbalance es extremo: solo 34 positivos en el periodo de prueba. Lo correcto no es compararlo contra un umbral absoluto sino contra el azar: es **22 veces mejor**, con intervalo de confianza calculado por *bootstrap* cuyo límite inferior sigue nueve veces por encima del azar. Y el KS de 0.74 y el PSI de 0.019 confirman que el ordenamiento es fuerte y estable. |
| **¿Por qué no usaste *accuracy*?** | Con un 0.38 % de positivos, un modelo que diga "todo normal" acierta el 99.6 % siendo inútil. Por eso uso PR-AUC y *recall* a tasa de falsos positivos fija. |
| **¿Cómo evitas la fuga de datos?** | Partición temporal estricta, la línea base de cada usuario excluye el día evaluado, y el grafo de referencia se congela al día anterior. Incluso documento en el reporte un caso donde **detecté y corregí** una fuga que yo mismo había introducido al elegir un parámetro mirando el conjunto de prueba. |
| **¿El 94 % de falsos positivos no es demasiado?** | Es el costo real del umbral actual y lo reporto sin filtrar. La curva de alertas por día permite al SOC elegir su punto de operación según su capacidad. Es un sistema de priorización, no de bloqueo automático. |
| **¿Qué harías con más tiempo?** | Enriquecer con las otras fuentes del mismo conjunto (procesos y flujos de red). Es la única palanca que añadiría señal nueva; probé tres alternativas de ajuste y ninguna generalizó. |
| **¿El caso que mostraste era un ataque real?** | Sí: **U-0737 es una cuenta genuinamente comprometida** y está en el primer lugar de la cola. Tuvo siete días en alerta durante el periodo, y **cinco de ellos tienen actividad de red team confirmada** (días 20, 22, 26, 27 y 29). El día de mayor puntuación (23) cae dentro de esa ventana de compromiso aunque no tenga un evento etiquetado ese día concreto. |
| **¿Por qué el grafo muestra solo 6 nodos rojos si en la diapositiva se ven decenas?** | Porque son casos distintos: la figura de la diapositiva es del periodo de entrenamiento, donde documenté un caso con 28 destinos nuevos de 49. En el periodo de prueba, este usuario abre 6 destinos nuevos. La señal es la misma —destinos que la cuenta jamás había tocado—, cambia la magnitud. |

---

## Recordatorios finales

- **Habla de "yo"**, no de "nosotros": el proyecto es individual.
- **No leas el guion**: úsalo para fijar el hilo y los números clave.
- Los números que debes tener memorizados: **40M tarjetas / $200M USD** (Target), **1,051M eventos**,
  **1 de cada 265** (desbalance), **U-0737 = posición #1 y compromiso real**, **riesgo 98**,
  **16 % vs 1.7 % vs 1.3 %** (NTLM: hoy / su base / sus pares), **20 alertas/día → 31 % de cuentas**.
- Si algo falla en vivo, **el asistente y las tres vistas son independientes**: si una tarda, pasa a
  otra y regresa. Y recuerda el punto 1 de la lista de arriba: despierta el backend antes.
