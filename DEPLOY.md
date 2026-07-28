# Guía de despliegue — Nexus Sentinel

Dos servicios independientes. **Despliega primero el backend**: el frontend necesita su URL pública
para poder configurarse.

```
[ Backend FastAPI ]  →  HF Spaces (Docker) o Render     →  URL de la API
        ↓ (VITE_API_URL)
[ Frontend React  ]  →  Vercel o Netlify                →  URL pública de la demo
```

---

## Parte 1 — Backend

Requisito previo: el repositorio debe estar en GitHub, y `docs/demo/snapshot.json` versionado
(ya lo está: es el dato que sirve la API).

### Opción A — Hugging Face Spaces (requiere cuenta verificada/PRO para Docker)

> ⚠️ En cuentas nuevas, el SDK **Docker** de HF Spaces aparece marcado como función de pago
> (PRO). Si tu cuenta no lo tiene habilitado, salta directo a la **Opción B (Render)** — es la
> ruta gratuita confirmada y la que se usó en este proyecto.

1. Crea una cuenta en <https://huggingface.co> y entra a **New → Space**.
2. Configura:
   - **Space name:** `nexus-sentinel-api`
   - **License:** MIT
   - **SDK:** selecciona **Docker** → *Blank*
   - **Visibility:** Public
3. HF crea un repo git vacío. Clónalo y copia dentro lo necesario:
   ```bash
   git clone https://huggingface.co/spaces/<tu-usuario>/nexus-sentinel-api
   cd nexus-sentinel-api

   # desde la raíz del proyecto Nexus Sentinel:
   cp -r <ruta-al-proyecto>/api          .
   cp -r <ruta-al-proyecto>/src          .
   mkdir -p docs/demo
   cp <ruta-al-proyecto>/docs/demo/snapshot.json docs/demo/
   cp <ruta-al-proyecto>/api/Dockerfile  ./Dockerfile   # HF lo busca en la raíz
   ```
4. Añade al inicio del `README.md` del Space esta cabecera (HF la usa para configurar el Space):
   ```yaml
   ---
   title: Nexus Sentinel API
   emoji: 🛡️
   colorFrom: blue
   colorTo: red
   sdk: docker
   app_port: 7860
   ---
   ```
5. Ajusta la ruta de copiado en el `Dockerfile`: como ahora la raíz del Space ES el proyecto,
   cambia `COPY api/requirements.txt ./api/requirements.txt` y las demás rutas si moviste archivos.
   *(Si copiaste respetando la estructura `api/`, `src/`, `docs/demo/`, el Dockerfile funciona
   tal cual.)*
6. Publica:
   ```bash
   git add . && git commit -m "Backend Nexus Sentinel" && git push
   ```
7. HF construye la imagen (2-4 min). Tu URL queda como:
   **`https://<tu-usuario>-nexus-sentinel-api.hf.space`**
8. **Verifica** antes de seguir:
   ```bash
   curl https://<tu-usuario>-nexus-sentinel-api.hf.space/health
   ```
   Debe responder `{"status":"ok","snapshot_cargado":true,...}`. La documentación interactiva queda
   en `…/docs`.

### Opción B — Render (recomendada: gratis, confirmado sin tarjeta)

Guía completa, campo por campo. Los nombres exactos pueden variar un poco si Render actualiza su
interfaz; si no ves un campo con ese nombre exacto, busca el más parecido en la misma sección.

**1. Cuenta e inicio**
1. Entra a **https://render.com**.
2. **Sign up** (recomendado: *"Sign up with GitHub"* — así en el mismo paso le das acceso a tus
   repos, incluido el privado). Si ya tienes cuenta, **Log in**.

**2. Crear el Web Service**
3. En el dashboard, botón **New +** (arriba a la derecha) → **Web Service**.
4. En *"Connect a repository"*, busca `nexus-sentinel` en la lista.
   - Si no aparece (por ser privado), haz clic en **Configure account** / **Edit GitHub App
     Permissions**, y en la pantalla de GitHub marca **Only select repositories** →
     selecciona `nexus-sentinel` → **Save**. Vuelves a Render y ya debería listarse.
5. Clic en **Connect** junto al repo.

**3. Formulario de configuración — cada campo:**

| Campo | Qué poner | Nota |
|---|---|---|
| **Name** | `nexus-sentinel-api` | Define parte de tu URL final |
| **Project** | (déjalo vacío / "No project") | No aplica para este caso |
| **Language** (o "Runtime") | **Docker** | ⚠️ El campo más importante: por defecto Render a veces preselecciona "Python 3" — CÁMBIALO a **Docker** explícitamente, si no, ignora el Dockerfile |
| **Branch** | `main` | La rama que ya tienes |
| **Region** | Oregon (US West) u otra cercana | Cualquiera con tier Free sirve |
| **Root Directory** | *(vacío)* | No lo uses; el contexto se define abajo |
| **Dockerfile Path** | `api/Dockerfile` | Ruta relativa a la raíz del repo |
| **Docker Build Context Directory** | `.` | Un punto: la raíz del repo completa (el Dockerfile necesita ver `api/`, `src/` y `docs/demo/`) |
| **Instance Type** | **Free** ($0/month) | Aparece como tarjeta seleccionable |

**4. Variables de entorno — antes de crear el servicio (o justo después):**

Busca la sección **Environment Variables** en el mismo formulario (a veces está más abajo, en un
bloque colapsable "Advanced"). Si no la ves ahí, la agregas en el Paso 6 después de crear el
servicio — el resultado es el mismo.

Clic en **Add Environment Variable** por cada una:

| Key | Value |
|---|---|
| `DEEPSEEK_API_KEY` | tu key completa, empieza con `sk-` |
| `CORS_ORIGINS` | `*` (lo restringimos en la Parte 3 de esta guía) |

⚠️ **Errores comunes que hacen que la key "no se vea" (el problema que ya tuvimos):**
- Pegar con un espacio en blanco al inicio o final del valor (revisa el campo con cuidado).
- Escribir el nombre distinto a `DEEPSEEK_API_KEY` (mayúsculas y guion bajo exactos).
- Agregar la variable y no darle a **Save Changes** — sin eso no se guarda.
- Agregarla en un servicio distinto al que estás probando (verifica la URL en la pestaña del
  navegador coincide con la que estás probando).

**5. Crear**
6. Baja hasta el final del formulario y haz clic en **Deploy Web Service** (o **Create Web
   Service**).
7. Vas a ver una pantalla de logs en vivo — Render construye la imagen Docker. Tarda 3-6 minutos
   la primera vez. Espera a ver `"Application startup complete"` o similar, y el estado pasa a
   **Live** (punto verde) en la parte superior.
8. Tu URL aparece arriba del todo, con el formato `https://nexus-sentinel-api-XXXX.onrender.com`
   (Render agrega un sufijo aleatorio si el nombre ya existe).

**6. Si necesitas agregar o corregir las variables DESPUÉS de crear el servicio:**
9. Dentro del servicio ya creado, ve a la pestaña **Environment** (menú lateral izquierdo).
10. Agrega o corrige `DEEPSEEK_API_KEY` / `CORS_ORIGINS` ahí.
11. Clic en **Save Changes**. Render dispara un redeploy automático (no reconstruye la imagen
    Docker desde cero, solo reinicia el contenedor con las nuevas variables — tarda ~1 min).

**7. Verificar que quedó bien:**
```bash
curl https://<tu-url>.onrender.com/health
curl https://<tu-url>.onrender.com/assistant/health
# el segundo debe responder {"disponible": true, "modelo": "deepseek-chat"}
```

> ⚠️ **Aviso del plan gratuito de Render:** el servicio se duerme tras 15 min de inactividad y la
> primera petición tarda ~50 s en despertarlo. Si vas a hacer una demo en vivo, **abre la URL unos
> minutos antes** para que esté caliente.

### Variables de entorno del backend

Configúralas en el panel del servicio (HF: *Settings → Variables and secrets*; Render: *Environment*).

| Variable | Valor recomendado | Para qué |
|---|---|---|
| `CORS_ORIGINS` | `https://tu-app.vercel.app` | **Importante:** restringe qué dominio puede consumir la API. Déjalo en `*` solo mientras pruebas. |
| `DEEPSEEK_API_KEY` | *(tu key, como **secreto**)* | Habilita el asistente conversacional. Ver más abajo cómo obtenerla. Sin ella, el asistente degrada con un aviso claro; el resto de la app funciona igual. |
| `SNAPSHOT_PATH` | *(no tocar)* | Ya viene configurada en el Dockerfile |

Configura `CORS_ORIGINS` **después** de desplegar el frontend, cuando ya conozcas su URL.

> 🔑 **Guárdala como secreto, no como variable normal.** En HF Spaces usa *Settings → Variables and
> secrets → New secret*; en Render marca la casilla *Secret*. Nunca la pongas en el código, en el
> frontend ni en un commit: quien tenga la key puede gastar tu cuota.

### Obtener la API key gratuita de DeepSeek (para el asistente)

El asistente conversacional (requerimiento del profesor) usa **DeepSeek**, cuya API es compatible
con el SDK de OpenAI y ofrece créditos gratuitos al registrarse.

1. Entra a <https://platform.deepseek.com> y crea una cuenta.
2. Ve a **API Keys → Create new API key**. Cópiala en el momento (solo se muestra una vez).
3. Pégala en la variable de entorno `DEEPSEEK_API_KEY` del backend (como secreto).
4. Reinicia el servicio. Verifica:
   ```bash
   curl https://<tu-backend>/assistant/health
   # → {"disponible": true, "modelo": "deepseek-chat"}
   ```

**Probar en local** (sin desplegar):
```bash
# PowerShell:
$env:DEEPSEEK_API_KEY = "sk-..."
uvicorn api.main:app --port 8000
# bash:
DEEPSEEK_API_KEY=sk-... uvicorn api.main:app --port 8000
```
Luego abre la consola, pulsa el botón 💬 y pregunta *"¿Quiénes son los usuarios de mayor riesgo?"*:
el asistente llamará a las herramientas de datos y responderá con las cifras reales del periodo.

> El modelo por defecto es `deepseek-chat`. Puedes cambiarlo con la variable `DEEPSEEK_MODEL`
> (p. ej. `deepseek-reasoner`). La key **solo vive en el backend**: el frontend nunca la ve.

---

## Parte 2 — Frontend

Requisito previo: la URL del backend funcionando (Parte 1).

### Opción A — Vercel (recomendada)

1. Entra a <https://vercel.com> → **Add New → Project** → importa tu repositorio de GitHub.
2. Configura:
   - **Root Directory:** `ui`  ← *importante, no la raíz del repo*
   - **Framework Preset:** Vite (lo detecta solo)
   - **Build Command:** `npm run build`
   - **Output Directory:** `dist`
3. En **Environment Variables** añade:
   | Name | Value |
   |---|---|
   | `VITE_API_URL` | `https://<tu-usuario>-nexus-sentinel-api.hf.space` |

   *(sin barra final)*
4. **Deploy**. Tu URL queda como `https://nexus-sentinel.vercel.app`.

El archivo `ui/vercel.json` ya está incluido: redirige todas las rutas a `index.html` para que
`/employee/U-0737` funcione al recargar la página (comportamiento necesario en una SPA).

### Opción B — Netlify

1. <https://netlify.com> → **Add new site → Import an existing project** → conecta GitHub.
2. Configura:
   - **Base directory:** `ui`
   - **Build command:** `npm run build`
   - **Publish directory:** `ui/dist`
3. En **Site settings → Environment variables** añade `VITE_API_URL` con la URL del backend.
4. **Deploy**. El archivo `ui/public/_redirects` ya maneja el enrutado de la SPA.

---

## Parte 3 — Cerrar el círculo (no te saltes esto)

1. **Restringe CORS.** Vuelve al backend y pon `CORS_ORIGINS` con la URL real del frontend. Si lo
   dejas en `*`, cualquier sitio puede consumir tu API.
2. **Verifica de punta a punta** abriendo la URL del frontend:
   - La barra superior debe mostrar `periodo D20–D29 · 3,328 usuarios` (si dice *"backend no
     disponible"*, el problema es `VITE_API_URL` o CORS).
   - `/triage`: la cola carga y al hacer clic en un usuario aparece su explicación SHAP.
   - `/employee/U-0737`: se dibuja el mini-grafo con nodos rojos.
   - `/executive`: cargan las gráficas de tendencia.
3. **Anota ambas URLs** — el plan pide la URL funcional como entregable (da puntos extra).

## Diagnóstico de problemas frecuentes

| Síntoma | Causa probable | Solución |
|---|---|---|
| "backend no disponible" en la barra superior | `VITE_API_URL` mal escrita o con barra final | Corrige la variable y **vuelve a desplegar** (Vite embebe las variables en tiempo de build) |
| Error de CORS en la consola del navegador | `CORS_ORIGINS` no incluye el dominio del frontend | Añade la URL exacta, con `https://` y sin barra final |
| Los cambios en la variable no surten efecto | Vite compila las variables en el build | Fuerza un *redeploy*, no basta con guardar la variable |
| La primera carga tarda ~50 s (Render) | El plan gratuito duerme el servicio | Normal; usa HF Spaces o precalienta antes de la demo |
| `/employee/U-0737` da 404 al recargar | Falta el redirect de SPA | Verifica que `vercel.json` o `public/_redirects` estén desplegados |
| El feedback del analista desaparece | Almacenamiento efímero en planes gratuitos | Esperado en la demo; en producción iría a una base de datos |

## Actualizar el despliegue

- **Cambió el modelo o el snapshot:** regenera con `python -m src.inference`, commitea
  `docs/demo/snapshot.json` y vuelve a desplegar el backend.
- **Cambió el contrato de la API:** regenera los tipos del frontend con `npm run gen:api` (desde
  `ui/`, con el backend corriendo o con el `openapi.json` actualizado) y despliega ambos.
