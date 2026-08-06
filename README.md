# Nexus Sentinel

**Detección de uso indebido de credenciales mediante analítica de comportamiento de usuarios y
entidades (UEBA).**

Sistema de puntuación de riesgo que identifica cuentas comprometidas analizando la *desviación* del
comportamiento de autenticación de cada usuario, sobre datos reales de una red corporativa.

| Entregable | Enlace |
|---|---|
| 🖥️ **Interfaz desplegada** | https://nexus-sentinel-iota.vercel.app |
| 🎬 **Video de presentación** | https://youtu.be/83_SxOdOjOc |
| ⚙️ **API (documentación interactiva)** | https://nexus-sentinel-api-2m8a.onrender.com/docs |
| 📓 **Notebook reproducible** | [`notebook/ueba_lanl_nexus_sentinel.ipynb`](notebook/ueba_lanl_nexus_sentinel.ipynb) |
| 📄 **Documento final** | [`docs/entregables/Documento - Nexus Sentinel.pdf`](docs/entregables/) |
| 🎤 **Presentación** | [`docs/entregables/Presentacion - Nexus Sentinel.pdf`](docs/entregables/) |
| 🔁 **Guía de reproducción** | [`REPRODUCIR.md`](REPRODUCIR.md) |

> **Nota sobre la primera carga:** el backend está desplegado en un plan gratuito que suspende el
> servicio tras 15 minutos de inactividad. La primera petición puede tardar hasta un minuto en
> despertarlo; la interfaz lo avisa en pantalla y carga los datos sola en cuanto responde.

---

## El problema

El perímetro de seguridad tradicional está diseñado para detener a un intruso que *rompe* algo. Pero
la mayoría de las brechas modernas no rompen nada: usan **credenciales legítimas** —robadas por
phishing, compradas o abusadas por un empleado— para moverse dentro de la red como un usuario normal.

El caso de Target (2013) lo ilustra: los atacantes robaron la credencial de un proveedor de
climatización y la usaron para alcanzar los puntos de venta de 1,797 tiendas. Estuvieron tres semanas
dentro. El resultado fueron 40 millones de tarjetas comprometidas y más de 200 millones de dólares en
pérdidas. Las alertas existían, pero nadie las investigó entre el ruido.

**El reto técnico:** ninguna autenticación individual viola una regla —la cuenta tiene permiso—. La
señal solo existe a nivel de **patrón de comportamiento**.

## La solución

Nexus Sentinel no vigila eventos: mide **desviaciones**. Para cada usuario construye una línea base
de comportamiento y evalúa, día a día, cuánto se aleja de ella.

```
1,051 M eventos de autenticación  →  cola priorizada y explicada de casos investigables
```

El sistema entrega, por cada **usuario-día**, una puntuación de riesgo de 0 a 100 acompañada
**siempre** de su explicación (valores SHAP), traducida a un semáforo operativo:

| Nivel | Significado | Acción |
|---|---|---|
| 🟢 Verde | Bajo el umbral de alerta | Registro pasivo; alimenta la línea base |
| 🟠 Naranja | Percentil calibrado a la capacidad del equipo | Ticket con evidencia y explicación |
| 🔴 Rojo | Casos prioritarios | Investigación con validación humana obligatoria |

**Principio de diseño:** el sistema prioriza y explica; **ninguna acción sobre una cuenta es
automática**. La decisión final siempre es de un analista.

## Resultados

Evaluación sobre un conjunto de prueba **fuera de tiempo** (días 20–29), nunca visto durante el
entrenamiento, la selección de modelo ni la calibración.

| Métrica | Valor | Lectura |
|---|---|---|
| **PR-AUC** (métrica rectora) | **0.056** | ~22× sobre un ordenamiento aleatorio (0.0025) |
| ROC-AUC | 0.939 | *Reportada con advertencia:* engaña con este desbalance |
| Recall @ FPR = 1 % | 0.34 | Un tercio de los días comprometidos dentro del 1 % de falsos positivos |
| **PSI** (estabilidad del score) | **0.019** | Estable entre periodos |
| **KS** (separación de clases) | **0.74** | Separación fuerte |

**El puente con el negocio** —la curva que traduce el modelo a decisiones operativas:

| Presupuesto de alertas | Cobertura de cuentas comprometidas |
|---|---|
| 20 alertas / día | 31 % |
| 30 alertas / día | 38 % |
| 100 alertas / día | 85 % |

> **Contexto honesto:** con solo 34 casos positivos en el conjunto de prueba, el intervalo de
> confianza del PR-AUC (bootstrap, 95 %) es `[0.022, 0.146]`. El límite inferior sigue estando nueve
> veces por encima del azar, por lo que la capacidad discriminativa es real, aunque el valor puntual
> tenga incertidumbre. El costo operativo también se reporta sin filtrar: al umbral naranja la
> precisión es baja (13 verdaderos positivos frente a 280 falsos positivos).

## Los datos

**Fuente:** Kent, A. D. (2015). *Comprehensive, Multi-Source Cyber-Security Events.* Los Alamos
National Laboratory. https://csr.lanl.gov/data/cyber1/

Datos **reales** de la red corporativa interna de LANL: 58 días consecutivos de eventos
desidentificados, con ataques de un equipo de *red team* como verdad de terreno.

| | Dataset completo | Muestra de trabajo |
|---|---|---|
| Eventos de autenticación | 1,051,430,459 | 37,580,871 |
| Usuarios | 12,425 | 4,104 |
| Periodo | 58 días | 30 días |
| Cuentas comprometidas | 104 | 104 (todas) |

**Muestreo justificado** (documentado, no oculto):
- **Ventana de 30 días:** verificado empíricamente que el 100 % de los eventos del *red team* ocurre
  entre los días 1 y 29 en el archivo completo.
- **Usuarios:** las 104 cuentas comprometidas + 4,000 usuarios normales muestreados con semilla fija,
  estratificados por cuartil de actividad.
- **Exclusiones:** cuentas de máquina (terminadas en `$`) y de sistema, ya que el scoring recae sobre
  personas.

**Desbalance resultante:** 181 de 47,956 usuario-días son maliciosos (**0.38 %**, 1 de cada 265).
Este número descarta la exactitud como métrica: un modelo que prediga «todo normal» acierta el
99.6 % siendo inútil.

## Metodología

### Ingeniería de variables — cuatro niveles de desviación

El núcleo técnico del proyecto. Cada nivel cubre un punto ciego que el anterior deja abierto:

| Nivel | Pregunta | Qué resuelve |
|---|---|---|
| **(a) Crudas** | ¿Qué hizo hoy? | Volumen, alcance, fallos, protocolo, horario |
| **(b) Desviación personal** | ¿Qué tan distinto de **su** pasado? | Lo normal es personal: 22 destinos son rutina para un admin y alarma para un contador |
| **(c) Desviación grupal** | ¿Qué tan distinto de **sus pares**? | Eventos globales legítimos (un *patch day* dispara a todos) |
| **(d) Novedad de grafo** | ¿Qué tan nuevo es su grafo de conexiones? | El atacante disciplinado mantiene volumen normal, pero no puede evitar tocar máquinas nuevas |

Resultado: **47,956 usuario-días × 61 variables**, sin valores faltantes.

### Reglas anti-fuga

La fuga temporal es el error más costoso en un problema con partición temporal e historia. Reglas
aplicadas y auditadas:

- Las estadísticas históricas excluyen el día evaluado (`shift(1)` sobre la serie del usuario).
- El grafo de referencia se **congela al día D−1** antes de evaluar el día D.
- Los perfiles del clustering de pares se ajustan **solo con días de entrenamiento**.
- Ninguna variable deriva del archivo de etiquetas.
- Partición **temporal estricta**, nunca aleatoria (los días de un usuario están autocorrelacionados).

### Modelos

| Modelo | Rol | PR-AUC (prueba) |
|---|---|---|
| **XGBoost calibrado** (isotónica) | Modelo central supervisado | **0.056** |
| K-Means (distancia al centroide) | Peer groups + score de anomalía | 0.093 |
| Isolation Forest | Línea base no supervisada | 0.027 |
| Random Forest / Regresión Logística | Referencias comparativas | — |

- **Desbalance:** `scale_pos_weight = 184.9`, calculado sobre el conjunto de entrenamiento.
- **Tres conjuntos temporales:** entrenamiento (días 0–13), validación (14–19), prueba (20–29). El
  corte de validación se eligió con datos: un corte en el día 16 la dejaba sin un solo positivo.
- **Búsqueda de hiperparámetros:** 40 configuraciones evaluadas sobre validación temporal, con
  detención temprana por PR-AUC.
- **Calibración:** isotónica vs. Platt decidido por *Brier score* en validación cruzada interna.

## Arquitectura

```
Datos crudos (LANL)
      │  descarga en streaming + lectura por chunks
      ▼
Muestreo documentado ──► auth_sample.parquet (37.6 M eventos)
      │
      ▼
Ingeniería de variables (4 niveles) ──► tabla usuario-día (47,956 × 61)
      │
      ▼
Modelado ──► artefactos serializados (XGBoost, IF, K-Means, explicador SHAP)
      │
      ▼
Inferencia ──► snapshot.json  ◄── el puente entre el modelo y la interfaz
      │
      ▼
API FastAPI (11 rutas, contrato OpenAPI) ──► UI React (3 vistas + asistente)
```

**División de responsabilidades:** el backend es dueño de todo el conocimiento del modelo
(puntuaciones, umbrales, explicaciones). El frontend consume y presenta; **nunca recalcula riesgo**.
Los tipos TypeScript se generan del contrato OpenAPI, de modo que un cambio en la API rompe el
*build* del frontend, no la demo en vivo.

### La interfaz

| Vista | Usuario objetivo | Contenido |
|---|---|---|
| `/triage` | Analista SOC | Cola priorizada, evolución del riesgo, panel «Qué disparó la alerta», acciones |
| `/employee/:id` | Analista SOC | Actividad del día, qué se salió de lo normal, **mapa de conexiones** |
| `/executive` | CISO | Tendencia por perfil de cuenta, cuentas críticas, eficiencia del equipo |

Incluye un **asistente conversacional** que responde preguntas en lenguaje natural consultando los
datos reales del modelo mediante *function calling* (no genera cifras inventadas).

**Lenguaje de la interfaz:** el usuario final es el analista de un SOC, no un científico de datos.
La interfaz habla de conducta observable y evidencia —«qué disparó la alerta», «lo habitual en la
cuenta», «cuentas similares»—, y deja los términos del método (SHAP, K-Means, modelo supervisado)
para esta documentación y el documento final, donde sí corresponden.

## Estructura del repositorio

```
nexus-sentinel/
├── README.md                      Este documento
├── REPRODUCIR.md                  Guía paso a paso para levantar todo desde cero
├── DEPLOY.md                      Despliegue en Render y Vercel
├── requirements.txt               Dependencias de Python, con versiones fijadas
│
├── .github/workflows/             Consulta periódica que evita que el backend se suspenda
│
├── notebook/
│   └── ueba_lanl_nexus_sentinel.ipynb   Narrativa completa de punta a punta; importa src/
│
├── src/                           Código de producción (lo reutilizan el notebook y la API)
│   ├── data.py                    Descarga en streaming, lectura por chunks, muestreo, Parquet
│   ├── eda.py                     Exploración, inferencia del ciclo circadiano, figuras 1-3
│   ├── features.py                Variables crudas, desviación personal y grupal, etiquetado
│   ├── graph.py                   Grafo usuario→computadora y variables de novedad
│   ├── models.py                  Isolation Forest, K-Means, XGBoost, evaluación, estabilidad
│   ├── inference.py               Puntuación 0-100, SHAP local, generación del snapshot
│   └── assistant.py               Asistente conversacional (function calling)
│
├── api/                           Backend FastAPI
│   ├── main.py                    11 rutas, esquemas Pydantic, contrato OpenAPI
│   ├── requirements.txt           Dependencias del backend (subconjunto ligero)
│   ├── Dockerfile                 Imagen que se despliega en Render
│   └── tests/test_api.py          23 pruebas de contrato
│
├── ui/                            Frontend React (Vite + TypeScript)
│   ├── src/api/                   Cliente tipado y schema.d.ts generado del OpenAPI
│   ├── src/features/              Las 3 vistas + asistente + componentes compartidos
│   └── public/                    Logotipo e iconos
│
├── intro-demo/                    Apertura de la demostración: el caso Target (React, local)
│
├── data/
│   ├── raw/redteam.txt.gz         Verdad de terreno original (8 KB, versionada)
│   └── work/                      Derivados versionados del muestreo:
│       ├── user_day_features.parquet    Tabla maestra 47,956 × 61 (5.1 MB)
│       ├── redteam.parquet              Etiquetas normalizadas
│       ├── sample_metadata.json         Trazabilidad del muestreo
│       └── features_metadata.json       Trazabilidad de las variables
│
├── models/                        Artefactos entrenados, VERSIONADOS (2.2 MB en total)
│   ├── fase4_artefactos.joblib    XGBoost calibrado, Isolation Forest, explicador SHAP
│   ├── inference_bundle.joblib    Umbrales y metadatos de la puntuación de riesgo
│   └── peer_kmeans.joblib         Modelo de perfiles de cuenta
│
└── docs/
    ├── eda/                       Figuras 1-3 del análisis exploratorio
    ├── modeling/                  Figuras 4-5 (evaluación y SHAP)
    ├── demo/snapshot.json         Datos que sirve la API (1.6 MB)
    └── entregables/               Documento final y presentación, en PDF
```

> **Lo único que no está en el repositorio** es `data/work/auth_sample.parquet` (200 MB, los eventos
> muestreados) por exceder el límite de tamaño de GitHub. Vive como adjunto de la
> [*release* v1.0](https://github.com/AAO-dev/nexus-sentinel/releases) y **el notebook lo descarga
> solo**. Todo lo demás —tabla de variables, modelos entrenados, snapshot y verdad de terreno— está
> versionado.

## Cómo reproducir el proyecto

📖 **Guía completa paso a paso: [`REPRODUCIR.md`](REPRODUCIR.md)** — instalación, notebook, pipeline,
backend, interfaz, verificación y solución de problemas.

**Requisitos:** Python 3.11 y Node.js 18 o superior.

El repositorio **versiona los artefactos intermedios**, así que no hace falta descargar nada pesado
salvo que quieras rehacer el muestreo desde la fuente original:

| Quiero reproducir… | Necesito descargar | Tiempo |
|---|---|---|
| **API e interfaz funcionando** | Nada, todo está en el repositorio | 5 minutos |
| **Modelado e inferencia** (reentrenar) | Nada, la tabla de variables está versionada | 10 minutos |
| **Análisis exploratorio e ingeniería de variables** | `auth_sample.parquet` (200 MB), que el notebook descarga solo | 15 minutos |
| **El muestreo desde el origen** | `auth.txt.gz` (7.2 GB) desde csr.lanl.gov | 1–2 horas |

### El camino más corto: ver el sistema funcionando

```bash
git clone https://github.com/AAO-dev/nexus-sentinel.git
cd nexus-sentinel
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
uvicorn api.main:app --port 8000
```

En Linux o macOS, la cuarta línea es `source .venv/bin/activate`.

El backend **funciona sin haber entrenado nada**, porque sirve el snapshot ya versionado. Con él
corriendo, en otra terminal:

```bash
cd ui
npm install
npm run dev
```

La consola queda en http://localhost:5173 y no requiere configurar variables de entorno: en
desarrollo, las peticiones a `/api` se redirigen solas al backend local.

### Verificar que todo quedó bien

```bash
pytest api/tests -q          # 23 pruebas de contrato del backend
cd ui && npm run typecheck   # tipos del frontend contra el contrato OpenAPI
cd ui && npm run build       # compilación de producción
```

## Despliegue

Instrucciones completas paso a paso en [`DEPLOY.md`](DEPLOY.md).

| Componente | Plataforma | Variables de entorno |
|---|---|---|
| Backend | Render (Docker) | `DEEPSEEK_API_KEY`, `CORS_ORIGINS` |
| Frontend | Vercel | `VITE_API_URL` |

El plan gratuito de Render suspende el servicio tras 15 minutos sin tráfico, y reactivarlo tarda
cerca de un minuto. Para que quien abra el enlace no se encuentre con una espera, una tarea
programada en `.github/workflows/` consulta el estado del servicio cada 10 minutos y evita que
llegue a dormirse.

## Limitaciones y trabajo futuro

- **Volumen de positivos:** con 181 eventos de compromiso en todo el conjunto, el margen estadístico
  es estrecho. Se probaron tres palancas de mejora (extender la ventana temporal, combinar
  puntuaciones supervisada y no supervisada, agregar el riesgo por cuenta) y **ninguna sobrevivió a
  una selección honesta en validación**.
- **Deriva entre campañas:** el análisis CSI detectó que dos variables (desviación de fallos y de
  NTLM respecto a los pares) derivan entre periodos, ya que dependen de *cómo* ataca el equipo
  ofensivo en cada campaña. El score agregado permanece estable.
- **Sesgo de la fuente:** el conjunto solo incluye fallos de autenticación de usuarios que tuvieron
  al menos un éxito, por lo que los ataques de adivinación contra cuentas inexistentes quedan fuera
  del alcance por diseño.
- **Trabajo futuro:** la única palanca que añadiría señal genuina es el enriquecimiento con las otras
  fuentes del mismo conjunto de LANL (eventos de procesos y flujos de red).

## Stack tecnológico

**Datos y modelado:** Python · pandas · polars · PyArrow · scikit-learn · XGBoost · SHAP · NetworkX
**Backend:** FastAPI · Pydantic · Uvicorn · pytest
**Frontend:** React 18 · TypeScript · Vite · TanStack Query · React Router · Recharts

## Referencias

- Kent, A. D. (2015). *Comprehensive, Multi-Source Cyber-Security Events* [Data set]. Los Alamos
  National Laboratory. https://csr.lanl.gov/data/cyber1/
- Chen, T., & Guestrin, C. (2016). XGBoost: A Scalable Tree Boosting System. *KDD '16*.
- Lundberg, S. M., & Lee, S.-I. (2017). A Unified Approach to Interpreting Model Predictions.
  *NeurIPS 30*.
- Liu, F. T., Ting, K. M., & Zhou, Z.-H. (2008). Isolation Forest. *ICDM '08*.
- Saito, T., & Rehmsmeier, M. (2015). The Precision-Recall Plot Is More Informative than the ROC Plot
  When Evaluating Binary Classifiers on Imbalanced Datasets. *PLoS ONE, 10*(3).

---

**Autor:** Arellano Ortiz Andre
**Diplomado en Ciencia de Datos, Generación 33** · Universidad Nacional Autónoma de México
