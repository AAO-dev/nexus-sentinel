/**
 * Barra de acciones del analista (sección 8.2) + historial de decisiones.
 *
 * Principio de diseño nº 3: "falso positivo" cierra el ciclo de retroalimentación. Y decisión de
 * diseño nº 3 del plan: human-in-the-loop — ninguna acción sobre la cuenta es automática; la UI
 * registra la decisión de una persona, no ejecuta bloqueos.
 */
import { useState } from 'react';

import type { Decision } from '../../api/client';
import { useFeedbackHistory, useSendFeedback } from '../../hooks/useApi';

const OPCIONES: { valor: Decision; texto: string; peligro?: boolean }[] = [
  { valor: 'falso_positivo', texto: 'Falso positivo' },
  { valor: 'investigar', texto: 'Abrir investigación' },
  { valor: 'escalar', texto: 'Escalar', peligro: true },
];

export function ActionBar({ employeeId, day }: { employeeId: string; day: number }) {
  const [nota, setNota] = useState('');
  const enviar = useSendFeedback(employeeId, day);
  const historial = useFeedbackHistory(employeeId, day);

  return (
    <div>
      <div className="filters">
        {OPCIONES.map((o) => (
          <button
            key={o.valor}
            className={`btn ${o.peligro ? 'danger' : ''}`}
            disabled={enviar.isPending}
            onClick={() => enviar.mutate({ decision: o.valor, nota: nota || undefined })}
          >
            {o.texto}
          </button>
        ))}
      </div>

      <input
        className="btn"
        style={{ width: '100%', textAlign: 'left', cursor: 'text' }}
        placeholder="Nota para la auditoría (opcional)"
        value={nota}
        maxLength={500}
        onChange={(e) => setNota(e.target.value)}
      />

      {enviar.isError && <p className="hint" style={{ color: 'var(--rojo-fg)' }}>No se pudo registrar la decisión.</p>}
      {enviar.isSuccess && <p className="hint">Decisión registrada. La cuenta no se modifica: la acción la ejecuta una persona.</p>}

      {historial.data && historial.data.length > 0 && (
        <div style={{ marginTop: 14 }}>
          <h3 style={{ fontSize: 13, margin: '0 0 6px', color: 'var(--ink-2)' }}>Historial de decisiones</h3>
          <table>
            <tbody>
              {historial.data.map((h, i) => (
                <tr key={i} style={{ cursor: 'default' }}>
                  <td style={{ fontWeight: 600 }}>{h.decision.replace('_', ' ')}</td>
                  <td>{h.analista}</td>
                  <td className="mono" style={{ fontSize: 12, color: 'var(--muted)' }}>
                    {new Date(h.timestamp).toLocaleString('es-MX')}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
