# Guía de despliegue — Nexus Sentinel

El sistema son dos servicios independientes. **Despliega primero el backend**: el frontend necesita
su URL pública para poder configurarse.

```
[ Backend FastAPI ]  →  Render (Docker)     →  URL de la API
        ↓ (VITE_API_URL)
[ Frontend React  ]  →  Vercel              →  URL pública de la aplicación
```

Requisito previo: el repositorio debe estar en GitHub y ser **público** (o dar acceso a las
plataformas), con `docs/demo/snapshot.json` versionado — es el dato que sirve la API.

---

## Parte 1 · Backend en Render

### 1. Cuenta y conexión

1. Entra a **https://render.com**.
2. **Sign up with GitHub** (recomendado): así autorizas el acceso a tus repositorios en el mismo
   paso. Si ya tienes cuenta, **Log in**.

### 2. Crear el servicio

3. En el panel, botón **New +** (arriba a la derecha) → **Web Service**.
4. Busca `nexus-sentinel` en la lista de repositorios.
   - Si no aparece, haz clic en **Configure account** / **Edit GitHub App Permissions**, marca
     **Only select repositories** → selecciona `nexus-sentinel` → **Save**, y vuelve a Render.
5. Clic en **Connect** junto al repositorio.

### 3. Configuración, campo por campo

| Campo | Valor | Nota |
|---|---|---|
| **Name** | `nexus-sentinel-api` | Define parte de la URL final |
| **Language** (o *Runtime*) | **Docker** | ⚠️ El campo más importante: Render suele preseleccionar «Python 3». Cámbialo a **Docker** o ignorará el Dockerfile |
| **Branch** | `main` | |
| **Region** | La más cercana | Cualquiera con nivel gratuito sirve |
| **Root Directory** | *(vacío)* | El contexto se define abajo |
| **Dockerfile Path** | `api/Dockerfile` | Ruta relativa a la raíz del repositorio |
| **Docker Build Context Directory** | `.` | Un punto: la raíz completa. El Dockerfile necesita ver `api/`, `src/` y `docs/demo/` |
| **Instance Type** | **Free** | |

### 4. Variables de entorno

Búscalas en el mismo formulario (a veces bajo un bloque **Advanced**) o añádelas después desde la
pestaña **Environment** del servicio.

| Variable | Valor | Para qué |
|---|---|---|
| `DEEPSEEK_API_KEY` | tu clave (empieza por `sk-`) | Habilita el asistente conversacional. Márcala como **Secret** |
| `CORS_ORIGINS` | `*` mientras pruebas | Se restringe al dominio real del frontend en la Parte 3 |

Las variables `SNAPSHOT_PATH`, `FEEDBACK_PATH` y `PORT` ya vienen configuradas en el Dockerfile y no
hay que tocarlas.

> ⚠️ **Errores frecuentes al pegar la clave:** un espacio en blanco al inicio o al final del valor,
> el nombre escrito distinto a `DEEPSEEK_API_KEY` (mayúsculas y guion bajo exactos), u olvidar pulsar
> **Save Changes**. Cualquiera de los tres hace que el asistente aparezca como no disponible.

### 5. Desplegar

6. Al final del formulario, **Deploy Web Service**.
7. Verás los registros en vivo mientras Render construye la imagen: tarda entre 3 y 6 minutos la
   primera vez. Espera a que el estado cambie a **Live** (punto verde).
8. Tu URL aparece arriba, con el formato `https://nexus-sentinel-api-XXXX.onrender.com` (Render
   añade un sufijo aleatorio si el nombre ya existe).

### 6. Si necesitas corregir variables después

9. Dentro del servicio, pestaña **Environment** en el menú lateral.
10. Corrige el valor y pulsa **Save Changes**. Render reinicia el contenedor con las nuevas
    variables sin reconstruir la imagen (aproximadamente un minuto).

### 7. Verificar

```bash
curl https://<tu-url>.onrender.com/health
curl https://<tu-url>.onrender.com/assistant/health
```

La primera debe responder `{"status":"ok","snapshot_cargado":true,...}` y la segunda
`{"disponible": true, "modelo": "deepseek-chat"}`. La documentación interactiva queda en `/docs`.

> ⚠️ **Sobre el nivel gratuito de Render:** el servicio se suspende tras 15 minutos de inactividad y
> la primera petición tarda hasta 50 segundos en reactivarlo. El frontend está preparado para esperar
> ese tiempo reintentando, pero **antes de una demostración en vivo conviene abrir la URL unos
> minutos antes** para que el servicio esté activo.

---

## Parte 2 · Frontend en Vercel

Requisito previo: la URL del backend funcionando.

1. Entra a **https://vercel.com** e inicia sesión con GitHub.
2. **Add New → Project** → importa `nexus-sentinel`.
3. Configura:

| Campo | Valor |
|---|---|
| **Root Directory** | `ui` ← pulsa **Edit** y escríbelo; por defecto Vercel usa la raíz, que no es donde vive el frontend |
| **Framework Preset** | Vite (lo detecta solo al fijar el Root Directory) |
| **Build Command** | `npm run build` |
| **Output Directory** | `dist` |

4. Despliega **Environment Variables** y añade:

| Name | Value |
|---|---|
| `VITE_API_URL` | `https://<tu-backend>.onrender.com` — **sin barra final** |

5. **Deploy**. Tarda uno o dos minutos. Tu URL queda como `https://nexus-sentinel.vercel.app`.

El archivo `ui/vercel.json` ya está incluido en el repositorio: redirige todas las rutas a
`index.html` para que direcciones como `/employee/U-0737` funcionen al recargar la página, que es el
comportamiento que necesita una aplicación de página única.

---

## Parte 3 · Cerrar el círculo

1. **Restringe CORS.** Vuelve al backend en Render → **Environment** → cambia `CORS_ORIGINS` de `*`
   a la URL exacta del frontend (`https://tu-app.vercel.app`, sin barra final) → **Save Changes**.
   Si lo dejas en `*`, cualquier sitio puede consumir tu API.

2. **Verifica de punta a punta** abriendo la URL del frontend:
   - La barra superior debe mostrar el periodo y el número de usuarios. Si dice *«backend no
     disponible»*, revisa `VITE_API_URL` y `CORS_ORIGINS`.
   - `/triage`: la cola carga y al seleccionar un usuario aparece su explicación.
   - `/employee/U-0737`: se dibuja el mini-grafo con los destinos nuevos marcados.
   - `/executive`: cargan las gráficas de tendencia.
   - El botón 💬 abre el asistente y responde a una pregunta.

3. **Anota ambas URLs**: son parte de los entregables del proyecto.

---

## Obtener la clave de DeepSeek

El asistente conversacional usa **DeepSeek**, cuya API es compatible con el SDK de OpenAI y ofrece
créditos al registrarse.

1. Entra a **https://platform.deepseek.com** y crea una cuenta.
2. Ve a **API Keys → Create new API key**. Cópiala en ese momento: solo se muestra una vez.
3. Comprueba en **Billing / Balance** que la cuenta tenga saldo disponible; sin él, la API responde
   con un error de saldo insuficiente.
4. Pégala en la variable `DEEPSEEK_API_KEY` del backend, como secreto.

**Probar en local antes de desplegar:**

```bash
# PowerShell
$env:DEEPSEEK_API_KEY = "sk-..."
uvicorn api.main:app --port 8000

# bash
DEEPSEEK_API_KEY=sk-... uvicorn api.main:app --port 8000
```

> La clave **vive solo en el backend**. El frontend nunca la ve: si estuviera en el navegador,
> cualquiera podría extraerla y consumir tu cuota. El modelo por defecto es `deepseek-chat` y puede
> cambiarse con la variable `DEEPSEEK_MODEL`.

---

## Diagnóstico de problemas

| Síntoma | Causa probable | Solución |
|---|---|---|
| «backend no disponible» en la barra superior | `VITE_API_URL` mal escrita o con barra final | Corrige la variable y **vuelve a desplegar**: Vite incrusta las variables durante la construcción |
| Error de CORS en la consola del navegador | `CORS_ORIGINS` no incluye el dominio del frontend | Añade la URL exacta, con `https://` y sin barra final |
| Los cambios de variables no surten efecto | Vite compila las variables en el *build* | Fuerza un nuevo despliegue; no basta con guardar la variable |
| La primera carga tarda casi un minuto | El nivel gratuito suspende el servicio | Es normal; abre la URL unos minutos antes de una demostración |
| `/employee/U-0737` da 404 al recargar | Falta la redirección de página única | Verifica que `ui/vercel.json` esté desplegado |
| El asistente responde «no configurado» | Falta `DEEPSEEK_API_KEY` o no se guardó | Revísala en **Environment** y guarda los cambios |
| El asistente da error de saldo | La cuenta de DeepSeek no tiene créditos | Revisa el balance en su plataforma |
| El feedback del analista desaparece | Almacenamiento efímero en el nivel gratuito | Esperado en la demostración; en producción iría a una base de datos |

---

## Actualizar el despliegue

- **Cambió el modelo o el snapshot:** regenera con `python -m src.inference`, confirma
  `docs/demo/snapshot.json` en el repositorio y empuja los cambios. Render redespliega solo.
- **Cambió el contrato de la API:** regenera los tipos del frontend con `npm run gen:api` desde
  `ui/` y despliega ambos servicios.
- **Cambió el conjunto de datos de trabajo:** súbelo como archivo adjunto de una nueva *release* y
  actualiza la URL en la celda de descarga del notebook.
