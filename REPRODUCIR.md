# Cómo reproducir Nexus Sentinel

Guía para levantar el proyecto completo desde cero: análisis, modelos, API e interfaz.

Está pensada para ejecutarse **sin conocimiento previo del proyecto** y sin credenciales de ningún
tipo. Cada paso indica qué produce y cómo comprobar que salió bien.

---

## Antes de empezar

| Requisito | Versión | Cómo comprobarlo |
|---|---|---|
| Python | 3.11 | `python --version` |
| Node.js | 18 o superior | `node --version` |
| Git | cualquiera reciente | `git --version` |

Espacio en disco: **1 GB** para la ruta normal. La ruta que regenera el muestreo desde la fuente
original necesita **10 GB** adicionales.

### Lo primero: elige hasta dónde quieres llegar

El repositorio incluye los artefactos intermedios ya calculados. Gracias a eso **no hace falta
descargar nada pesado** salvo que quieras rehacer el muestreo desde el archivo original de LANL.

| Quiero reproducir… | Qué necesito descargar | Cuánto tarda |
|---|---|---|
| **API e interfaz funcionando** | Nada, ya está todo en el repositorio | 5 minutos |
| **Modelado e inferencia** (reentrenar) | Nada, la tabla de variables está versionada | 10 minutos |
| **Análisis exploratorio y variables** | `auth_sample.parquet`, 200 MB, lo descarga el notebook solo | 15 minutos |
| **El muestreo desde el origen** | `auth.txt.gz`, 7.2 GB, desde csr.lanl.gov | 1 a 2 horas |

Si solo quieres ver el sistema funcionando, con los pasos 1, 4 y 5 es suficiente.

---

## Paso 1 · Clonar e instalar

```bash
git clone https://github.com/AAO-dev/nexus-sentinel.git
cd nexus-sentinel
```

```bash
python -m venv .venv
```

Activar el entorno virtual, según el sistema:

```bash
.venv\Scripts\activate
```

```bash
source .venv/bin/activate
```

La primera línea es para Windows; la segunda, para Linux o macOS.

```bash
pip install -r requirements.txt
```

Las versiones están fijadas a las que produjeron los resultados publicados, así que la instalación
es determinista.

**Comprobación:** debe responder sin error y listar las mismas versiones del archivo.

```bash
python -c "import pandas, xgboost, shap; print('dependencias OK')"
```

---

## Paso 2 · Ejecutar el notebook

Es el recorrido narrado de punta a punta: datos, exploración, ingeniería de variables, modelado,
inferencia y consumo desde la API.

El archivo es `notebook/ueba_lanl_nexus_sentinel.ipynb` y se puede abrir de tres formas:

- **VS Code** — ábrelo y selecciona el intérprete `.venv` como kernel.
- **Google Colab** — súbelo; funciona sin configuración previa (ver la nota más abajo).
- **Jupyter clásico** — requiere instalarlo aparte con `pip install notebook`, y luego:

```bash
jupyter notebook notebook/ueba_lanl_nexus_sentinel.ipynb
```

### Las dos rutas del notebook

El notebook ofrece dos caminos y explica la decisión en su propio texto:

- **Ruta rápida (por defecto).** Descarga sola el conjunto de trabajo `auth_sample.parquet` desde
  los archivos adjuntos de la [*release* v1.0](https://github.com/AAO-dev/nexus-sentinel/releases).
  Por eso **corre tal cual en un Google Colab recién abierto**, sin credenciales ni configuración.
- **Ruta larga.** Regenera el muestreo desde `auth.txt.gz` (7.2 GB) descargándolo de la fuente
  original de LANL. Solo si quieres verificar el muestreo desde el origen.

**Comprobación:** el notebook debe ejecutarse de principio a fin sin errores. Las cifras clave que
deben aparecer son 47,956 usuario-días por 61 variables, y 181 días con compromiso.

---

## Paso 3 · Ejecutar el pipeline por módulos

Alternativa al notebook, útil para regenerar un artefacto concreto. Cada módulo escribe sus salidas
y puede ejecutarse por separado siempre que existan las entradas del anterior.

```bash
python -m src.data
```
Descarga y muestreo → `data/work/auth_sample.parquet`

```bash
python -m src.eda
```
Exploración y figuras 1 a 3 → `docs/eda/`

```bash
python -m src.features
```
Tabla maestra de variables → `data/work/user_day_features.parquet` y `models/peer_kmeans.joblib`

```bash
python -m src.models
```
Entrenamiento, evaluación y estabilidad → `models/fase4_artefactos.joblib` y `docs/modeling/`

```bash
python -m src.inference
```
Puntuación y snapshot → `docs/demo/snapshot.json` y `models/inference_bundle.joblib`

> Los pasos `src.data` y `src.eda` son los únicos que necesitan el archivo de 200 MB. Desde
> `src.features` en adelante todo parte de artefactos ya versionados en el repositorio.

---

## Paso 4 · Levantar el backend

```bash
uvicorn api.main:app --port 8000
```

**Funciona sin haber entrenado nada**, porque sirve el snapshot que ya está versionado.

**Comprobación:** abre http://localhost:8000/docs para la documentación interactiva, o pide el
estado del servicio:

```bash
curl http://localhost:8000/health
```

Debe responder `{"status":"ok","snapshot_cargado":true,...}`.

Y las pruebas de contrato deben pasar completas:

```bash
pytest api/tests -q
```

**Resultado esperado: 23 pruebas en verde.**

### Asistente conversacional (opcional)

El asistente necesita una clave de DeepSeek en la variable de entorno `DEEPSEEK_API_KEY`. Sin ella,
esa única ruta responde `503` y **todo lo demás sigue funcionando con normalidad**. Cómo obtenerla:
sección correspondiente de [DEPLOY.md](DEPLOY.md).

---

## Paso 5 · Levantar la interfaz

Con el backend del paso 4 corriendo, en otra terminal:

```bash
cd ui
```

```bash
npm install
```

```bash
npm run dev
```

Queda en http://localhost:5173. En desarrollo **no hay que configurar variables de entorno**: Vite
redirige las peticiones `/api` al backend local automáticamente.

**Comprobación:** la barra superior debe mostrar el periodo y el número de usuarios, y la cola de
triage debe llenarse. Prueba las tres vistas: `/triage`, `/employee/U-0737` y `/executive`.

---

## Paso 6 · Apertura de la demostración (opcional)

Página independiente que presenta el caso de negocio antes de mostrar la consola. Corre en local y
no depende de la API.

```bash
cd intro-demo
```

```bash
npm install
```

```bash
npm run dev
```

Queda en http://localhost:5174, en un puerto distinto para poder tenerla abierta junto a la consola.

---

## Verificación final

Los tres comandos que confirman que todo está sano:

```bash
pytest api/tests -q
```

```bash
cd ui && npm run typecheck
```

```bash
cd ui && npm run build
```

El `typecheck` es especialmente informativo: los tipos del frontend se generan del contrato OpenAPI
del backend, así que si ambos dejaran de coincidir, la compilación fallaría.

---

## Si algo sale mal

| Síntoma | Causa probable | Solución |
|---|---|---|
| `ModuleNotFoundError` al ejecutar `src.*` | El entorno virtual no está activo | Actívalo y reinstala las dependencias |
| Los módulos `src.*` no se encuentran | Se está ejecutando desde otra carpeta | Ejecuta siempre desde la raíz del repositorio |
| El backend no arranca: no encuentra el snapshot | Falta `docs/demo/snapshot.json` | Debería estar versionado; si lo borraste, regenéralo con `python -m src.inference` |
| La interfaz no muestra datos en local | El backend no está corriendo | Levántalo primero (paso 4) y recarga |
| `npm install` falla | Versión de Node anterior a la 18 | Actualiza Node |
| El notebook falla al descargar el conjunto de datos | Sin conexión o la *release* cambió | Descarga `auth_sample.parquet` a mano desde las *releases* y colócalo en `data/work/` |
| El asistente responde 503 | Falta `DEEPSEEK_API_KEY` | Es el comportamiento esperado sin clave; el resto funciona igual |

---

## Qué está versionado y qué no

Saber esto explica por qué la reproducción es tan rápida.

| Artefacto | Tamaño | Dónde vive |
|---|---|---|
| `data/work/user_day_features.parquet` — tabla maestra | 5.1 MB | En el repositorio |
| `data/work/redteam.parquet` y metadatos del muestreo | < 100 KB | En el repositorio |
| `data/raw/redteam.txt.gz` — verdad de terreno original | 8 KB | En el repositorio |
| `models/*.joblib` — modelos entrenados y explicador | 2.2 MB | En el repositorio |
| `docs/demo/snapshot.json` — datos que sirve la API | 1.6 MB | En el repositorio |
| `data/work/auth_sample.parquet` — eventos muestreados | 200 MB | Adjunto de la *release*, lo descarga el notebook |
| `auth.txt.gz` — fuente original de LANL | 7.2 GB | Se descarga de csr.lanl.gov con `src/data.py` |

El único archivo que no está en el repositorio es el de 200 MB, porque excede el límite de tamaño de
GitHub. Todo lo demás viaja con el código.
