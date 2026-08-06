/**
 * Cliente HTTP tipado contra el backend del proyecto.
 *
 * Los tipos NO se escriben a mano: se generan del OpenAPI del backend con
 * `npm run gen:api`. Así, si el contrato cambia, rompe el build del frontend —
 * no la demo en vivo: es la separación de responsabilidades del sistema.
 */
import type { components } from './schema';

type S = components['schemas'];

export type Nivel = S['Nivel'];
export type Decision = S['Decision'];
export type Overview = S['Overview'];
export type EmpleadoCola = S['EmpleadoCola'];
export type SerieRiesgo = S['SerieRiesgo'];
export type Explicacion = S['Explicacion'];
export type Actividad = S['Actividad'];
export type EgoGraph = S['EgoGraph'];
export type KpisSoc = S['KpisSoc'];
export type PuntoCluster = S['PuntoCluster'];
export type ContribucionShap = S['ContribucionShap'];
export type FeedbackRegistro = S['FeedbackRegistro'];
export type Health = S['Health'];
export type ChatOut = S['ChatOut'];
export type MensajeChat = S['MensajeChat'];

/** En desarrollo se usa el proxy /api de Vite; en producción, VITE_API_URL. */
export const API_BASE = import.meta.env.VITE_API_URL || '/api';

export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly detail: string,
  ) {
    super(detail);
    this.name = 'ApiError';
  }
}

/**
 * Sin límite de tiempo, una conexión que queda abierta sin responder bloquea la consulta para
 * siempre: no falla, así que no se reintenta, y la interfaz se queda esperando indefinidamente.
 * Es justo lo que ocurre cuando el backend está suspendido. Con un corte explícito la petición
 * falla, el reintento se dispara y la aplicación se recupera sola.
 */
const ESPERA_MAX_MS = 20_000;

async function request<T>(path: string, init?: RequestInit & { esperaMs?: number }): Promise<T> {
  const { esperaMs = ESPERA_MAX_MS, ...resto } = init ?? {};
  const corte = new AbortController();
  const temporizador = setTimeout(() => corte.abort(), esperaMs);

  let res: Response;
  try {
    res = await fetch(`${API_BASE}${path}`, {
      ...resto,
      signal: corte.signal,
      headers: { 'Content-Type': 'application/json', ...resto.headers },
    });
  } finally {
    clearTimeout(temporizador);
  }
  if (!res.ok) {
    let detail = `Error ${res.status}`;
    try {
      const body = await res.json();
      detail = typeof body.detail === 'string' ? body.detail : detail;
    } catch {
      /* respuesta sin cuerpo JSON */
    }
    throw new ApiError(res.status, detail);
  }
  return res.json() as Promise<T>;
}

export const api = {
  health: () => request<Health>('/health'),
  overview: () => request<Overview>('/overview'),

  employees: (params: { level?: Nivel; limit?: number; sort?: 'risk' | 'alertas' } = {}) => {
    const q = new URLSearchParams();
    if (params.level) q.set('level', params.level);
    if (params.limit) q.set('limit', String(params.limit));
    if (params.sort) q.set('sort', params.sort);
    return request<EmpleadoCola[]>(`/employees?${q}`);
  },

  risk: (id: string, days = 30) => request<SerieRiesgo>(`/employees/${id}/risk?days=${days}`),
  explanation: (id: string, date: number) =>
    request<Explicacion>(`/employees/${id}/explanation?date=${date}`),
  activity: (id: string, date: number) =>
    request<Actividad>(`/employees/${id}/activity?date=${date}`),

  assistantHealth: () => request<{ disponible: boolean; modelo: string }>('/assistant/health'),
  assistantChat: (messages: MensajeChat[]) =>
    // El modelo puede encadenar varias llamadas a herramientas antes de responder: necesita
    // bastante más margen que una lectura del snapshot.
    request<ChatOut>('/assistant/chat', {
      method: 'POST',
      body: JSON.stringify({ messages }),
      esperaMs: 90_000,
    }),

  feedbackHistory: (caseId: string) =>
    request<FeedbackRegistro[]>(`/cases/${encodeURIComponent(caseId)}/feedback`),
  sendFeedback: (caseId: string, body: { decision: Decision; analista?: string; dia?: number; nota?: string }) =>
    request<{ registrado: boolean }>(`/cases/${encodeURIComponent(caseId)}/feedback`, {
      method: 'POST',
      body: JSON.stringify(body),
    }),
};

/** Un caso se identifica por empleado + día: es la unidad de decisión del SOC. */
export const caseId = (employeeId: string, day: number) => `${employeeId}-d${day}`;
