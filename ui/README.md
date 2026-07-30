# UI — Nexus Sentinel

Consola del analista SOC en **React 18 + Vite + TypeScript**. Consume la API del proyecto y presenta
la cola de triage priorizada y explicada.

> Despliegue paso a paso: [DEPLOY.md](../DEPLOY.md) en la raíz del proyecto.

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
Si un número no viene de la API, no existe. Todo el conocimiento de ML vive en el backend
es la separación de responsabilidades que gobierna el sistema.

## Estructura

```
src/
├── api/
│   ├── client.ts      # cliente HTTP tipado
│   └── schema.d.ts    # GENERADO — no editar a mano
├── components/ui.tsx  # presentacionales compartidos (KpiCard, RiskBadge, estados de carga/error)
├── features/
│   ├── shared/        # ShapExplainer, RiskTimeline, ActionBar
│   ├── triage/        # Vista 1
│   ├── investigation/ # Vista 2 (incluye EgoGraphMini)
│   └── executive/     # Vista 3
├── hooks/useApi.ts    # todas las llamadas al backend pasan por aquí
├── App.tsx            # layout y rutas
└── styles.css         # paleta del proyecto
```

## Las 3 vistas

| Ruta | Vista | Qué resuelve |
|---|---|---|
| `/triage` | Consola de triage | Cola priorizada con motivo en una línea, evolución del riesgo, explicación SHAP y acciones del analista |
| `/employee/:id` | Investigación | Actividad del día, comparativa vs. línea base personal y peer group, **mini-grafo ego** e historial de decisiones |
| `/executive` | Panel ejecutivo | Tendencia por rol conductual, cuentas de mayor riesgo y eficiencia del SOC |

Además, un **asistente conversacional** flotante (botón 💬, presente en todas las vistas) responde
preguntas del usuario y sirve de guía. Habla con `POST /assistant/chat`; la API key de DeepSeek vive
solo en el backend. Si no está configurada, el widget se muestra deshabilitado con un aviso claro.

### Principios de diseño aplicados
1. **Ninguna puntuación sin explicación** — el riesgo siempre aparece junto a su nivel y su SHAP.
2. **Semáforo 1:1 con los accionables** — verde (pasivo) / naranja (ticket) / rojo (prioritario).
3. **"Falso positivo" cierra el ciclo** — el feedback invalida la caché de la cola.
4. **IDs anonimizados** (`U-####`) — la fuente ya viene desidentificada.
5. **Human-in-the-loop** — la UI registra decisiones de personas; nunca ejecuta bloqueos de cuentas.

## Plan B para la demo

Streamlit sigue contemplado como MVP alternativo (`ui/streamlit_mvp/`, no implementado): si la demo
en vivo falla por red, un script local que lea el mismo `snapshot.json` cubre el expediente.
