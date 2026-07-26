/**
 * Hooks de estado de servidor (TanStack Query).
 *
 * Toda llamada al backend pasa por aquí: los componentes son presentacionales y reciben datos por
 * props o por estos hooks, nunca hacen fetch sueltos. La caché evita repetir peticiones al navegar
 * entre vistas, y la invalidación tras el feedback mantiene la cola de triage coherente.
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { api, caseId, type Decision, type Nivel } from '../api/client';

/** El snapshot es estático durante la demo: no tiene sentido refetch agresivo. */
const ESTABLE = { staleTime: 5 * 60 * 1000, retry: 1 } as const;

/**
 * Backends en planes gratuitos (Render) se duermen tras ~15 min de inactividad y tardan hasta
 * ~50s en despertar en la primera petición. Sin esto, la app se rinde tras 1 reintento (~1-3s) y
 * queda mostrando "backend no disponible" aunque el servidor ya haya despertado — el usuario tiene
 * que recargar manualmente. Con 6 reintentos y el backoff exponencial de TanStack Query
 * (1s, 2s, 4s, 8s, 16s, 30s ≈ 61s acumulados) la app sigue mostrando "conectando…" hasta que el
 * backend responde, sin intervención manual. Se aplica solo a las queries del primer render.
 */
const TOLERANTE_A_COLD_START = { staleTime: 5 * 60 * 1000, retry: 6 } as const;

export const useHealth = () =>
  useQuery({ queryKey: ['health'], queryFn: api.health, ...TOLERANTE_A_COLD_START });

export const useAssistantHealth = () =>
  useQuery({ queryKey: ['assistant-health'], queryFn: api.assistantHealth, ...TOLERANTE_A_COLD_START });

export const useOverview = () =>
  useQuery({ queryKey: ['overview'], queryFn: api.overview, ...TOLERANTE_A_COLD_START });

export const useTriageQueue = (level?: Nivel, limit = 50) =>
  useQuery({
    queryKey: ['employees', level ?? 'todos', limit],
    queryFn: () => api.employees({ level, limit }),
    ...TOLERANTE_A_COLD_START,
  });

export const useEmployeeRisk = (id: string | undefined, days = 30) =>
  useQuery({
    queryKey: ['risk', id, days],
    queryFn: () => api.risk(id!, days),
    enabled: Boolean(id),
    ...ESTABLE,
  });

export const useExplanation = (id: string | undefined, date: number | undefined) =>
  useQuery({
    queryKey: ['explanation', id, date],
    queryFn: () => api.explanation(id!, date!),
    enabled: Boolean(id) && date !== undefined,
    retry: false, // un 409 (día verde) es respuesta esperada, no un fallo a reintentar
    staleTime: ESTABLE.staleTime,
  });

export const useActivity = (id: string | undefined, date: number | undefined) =>
  useQuery({
    queryKey: ['activity', id, date],
    queryFn: () => api.activity(id!, date!),
    enabled: Boolean(id) && date !== undefined,
    retry: false,
    staleTime: ESTABLE.staleTime,
  });

export const useFeedbackHistory = (id: string | undefined, date: number | undefined) =>
  useQuery({
    queryKey: ['feedback', id, date],
    queryFn: () => api.feedbackHistory(caseId(id!, date!)),
    enabled: Boolean(id) && date !== undefined,
    staleTime: 0, // el historial debe reflejar de inmediato lo que el analista acaba de decidir
  });

export function useSendFeedback(id: string | undefined, date: number | undefined) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: { decision: Decision; nota?: string }) =>
      api.sendFeedback(caseId(id!, date!), { ...body, dia: date }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['feedback', id, date] });
      qc.invalidateQueries({ queryKey: ['employees'] });
    },
  });
}
