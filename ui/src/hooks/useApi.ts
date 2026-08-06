/**
 * Hooks de estado de servidor (TanStack Query).
 *
 * Toda llamada al backend pasa por aquí: los componentes son presentacionales y reciben datos por
 * props o por estos hooks, nunca hacen fetch sueltos. La caché evita repetir peticiones al navegar
 * entre vistas, y la invalidación tras el feedback mantiene la cola de triage coherente.
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useEffect } from 'react';

import { api, caseId, type Decision, type Nivel } from '../api/client';

/** El snapshot es estático durante la demo: no tiene sentido refetch agresivo. */
const ESTABLE = { staleTime: 5 * 60 * 1000, retry: 1 } as const;

/**
 * Backends en planes gratuitos (Render) se duermen tras ~15 min de inactividad y el arranque de la
 * imagen puede pasar de un minuto. Sin tolerancia, la app se rinde en segundos y queda mostrando un
 * error aunque el servidor ya haya despertado, obligando a recargar a mano.
 *
 * Con 10 reintentos y la espera creciente acotada a 12s (1, 2, 4, 8 y luego 12 fijos ≈ 87s
 * acumulados) la app espera todo el arranque en frío por sí sola.
 */
const TOLERANTE_A_COLD_START = {
  staleTime: 5 * 60 * 1000,
  retry: 4,
  retryDelay: (intento: number) => Math.min(1000 * 2 ** intento, 5_000),
  // Red de seguridad: mientras no haya una respuesta buena se vuelve a preguntar cada 5 s, así que
  // la app se recupera sola aunque el servidor tarde varios minutos en arrancar. Se mantiene
  // también con la pestaña en segundo plano, porque es habitual abrir el enlace, irse a otra
  // pestaña mientras despierta y volver esperando encontrarlo cargado.
  refetchInterval: (query: { state: { status: string } }) =>
    query.state.status === 'success' ? false : 5_000,
  refetchIntervalInBackground: true,
} as const;

export const useHealth = () =>
  useQuery({ queryKey: ['health'], queryFn: api.health, ...TOLERANTE_A_COLD_START });

/**
 * Estado del backend para la interfaz. Se considera "despertando" cualquier situación en la que
 * aún no hay respuesta buena pero ya hubo al menos un intento fallido, sin separar el error del
 * reintento: el sondeo sigue insistiendo en ambos casos, y mostrar un error mientras se sigue
 * intentando haría creer que la aplicación está rota.
 */
export function useEstadoBackend() {
  const salud = useHealth();
  const qc = useQueryClient();
  const listo = salud.isSuccess;
  const { refetch } = salud;

  // Bucle de recuperación propio. No se delega en la programación interna de reintentos porque
  // basta con que una petición quede en un estado sin resolver para que deje de reprogramarse y
  // la vista se congele. Aquí se pregunta cada 5 s hasta obtener respuesta, pase lo que pase.
  useEffect(() => {
    if (listo) return;
    const id = window.setInterval(() => void refetch(), 5_000);
    return () => window.clearInterval(id);
  }, [listo, refetch]);

  // En cuanto el servicio responde, el resto de consultas pueden haberse quedado en error: se
  // refrescan una sola vez para que la interfaz se llene sola, sin que nadie recargue.
  useEffect(() => {
    if (listo) void qc.refetchQueries();
  }, [listo, qc]);

  return {
    despertando: !listo && salud.failureCount > 0,
    listo,
    datos: salud.data,
  };
}

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
