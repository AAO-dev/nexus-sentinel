# UI — Nexus Sentinel

Consola del analista SOC en **React 18 + Vite + TypeScript**. Consume la API del proyecto y presenta
la cola de triage priorizada y explicada.

> Reproducir el proyecto completo: [REPRODUCIR.md](../REPRODUCIR.md) · Despliegue paso a paso:
> [DEPLOY.md](../DEPLOY.md), ambos en la raíz del proyecto.

## Arranque rápido

```bash
# 1) backend corriendo (desde la raíz del proyecto)
uvicorn api.main:app --port 8000

# 2) frontend
cd ui
npm install
npm run dev        # http://localhost:5173
```

En desarrollo no hace falta configurar nada: Vite redirige `/api` al backend local
(ver `vite.config.ts`). En producción se usa `VITE_API_URL` (ver `.env.example`).

## Scripts

| Comando | Qué hace |
|---|---|
| `npm run dev` | Servidor de desarrollo con recarga en caliente |
| `npm run build` | Bundle de producción en `dist/` |
| `npm run typecheck` | TypeScript estricto, sin emitir |
| `npm run gen:api` | **Regenera los tipos desde `openapi.json`** del backend |

## Decisiones de arquitectura

| Pieza | Elección | Por qué |
|---|---|---|
| Tipos | Generados del OpenAPI (`openapi-typescript`) | El contrato es código: si el backend cambia, rompe el build del frontend, no la demo en vivo |
| Estado de servidor | TanStack Query | Caché entre vistas, reintentos, e invalidación de la cola tras registrar feedback |
| Estado local | Hooks de React | No hay estado global que justifique Redux |
| Routing | React Router + `React.lazy` | Una ruta por vista, con code-splitting (cada vista pesa ~4-6 kB) |
| Gráficas | Recharts | Timeline de riesgo y tendencias; el grafo ego es SVG propio |

**Regla que gobierna todo el frontend:** la UI **nunca recalcula riesgo, umbrales ni explicaciones**.
Si un número no viene de la API, no existe. Todo el conocimiento del modelo vive en el backend: esa
separación de responsabilidades es la que gobierna el sistema.

## Estructura

```
src/
├── api/
│   ├── client.ts      # cliente HTTP tipado
│   └── schema.d.ts    # GENERADO — no editar a mano
├── components/ui.tsx  # presentacionales compartidos (KpiCard, RiskBadge, estados de carga/error)
├── features/
│   ├── shared/        # ShapExplainer, RiskTimeline, ActionBar, perfiles.ts
│   ├── triage/        # Vista 1
│   ├── investigation/ # Vista 2 (incluye EgoGraphMini)
│   ├── executive/     # Vista 3
│   └── assistant/     # Widget conversacional flotante
├── hooks/useApi.ts    # todas las llamadas al backend pasan por aquí
├── App.tsx            # layout y rutas
└── styles.css         # paleta del proyecto
```

## Las 3 vistas

| Ruta | Vista | Qué resuelve |
|---|---|---|
| `/triage` | Consola de triage | Cola priorizada con el motivo en una línea, evolución del riesgo, panel «Qué disparó la alerta» y acciones del analista |
| `/employee/:id` | Investigación | Actividad del día, qué se salió de lo normal, **mapa de conexiones** e historial de decisiones |
| `/executive` | Panel ejecutivo | Tendencia por perfil de cuenta, cuentas de mayor riesgo y eficiencia del SOC |

> **Lenguaje de la interfaz:** el usuario final es el analista de un SOC, no un científico de datos.
> Las vistas hablan de conducta observable y evidencia; los términos del método —SHAP, K-Means,
> modelo supervisado— se quedan en el código y en la documentación, donde sí corresponden. El
> módulo `features/shared/perfiles.ts` es el ejemplo: traduce los grupos del modelo a nombres
> legibles como «cuentas de uso intensivo y continuo».

Además, un **asistente conversacional** flotante (botón 💬, presente en todas las vistas) responde
preguntas del usuario y sirve de guía. Habla con `POST /assistant/chat`; la API key de DeepSeek vive
solo en el backend. Si no está configurada, el widget se muestra deshabilitado con un aviso claro.

### Principios de diseño aplicados
1. **Ninguna puntuación sin evidencia** — el riesgo siempre aparece junto a su nivel y a lo que lo
   disparó.
2. **Semáforo 1:1 con los accionables** — verde (pasivo) / naranja (ticket) / rojo (prioritario).
3. **"Falso positivo" cierra el ciclo** — el feedback invalida la caché de la cola.
4. **IDs anonimizados** (`U-####`) — la fuente ya viene desidentificada.
5. **Human-in-the-loop** — la UI registra decisiones de personas; nunca ejecuta bloqueos de cuentas.

## Tolerancia al arranque en frío

El backend desplegado vive en un plan gratuito que lo suspende tras un rato sin uso. La interfaz
está preparada para eso: las peticiones tienen un límite de tiempo explícito —sin él, una conexión
que queda abierta sin responder bloquearía la vista indefinidamente—, se insiste cada pocos segundos
hasta obtener respuesta, y mientras tanto se muestra un aviso que explica la espera en lugar de un
error. Los datos entran solos, sin que nadie tenga que recargar.
