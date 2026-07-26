/**
 * Explicación SHAP del usuario-día.
 *
 * Principio de diseño nº 1 del plan: ninguna puntuación sin explicación. Cada contribución se
 * muestra con su magnitud relativa y —lo que realmente permite decidir al analista— el valor del
 * día frente a su propio promedio histórico y al de su peer group conductual.
 */
import type { Explicacion } from '../../api/client';

const fmt = (v: number | null | undefined) =>
  v === null || v === undefined ? '—' : Math.abs(v) >= 100 ? v.toFixed(0) : v.toFixed(2);

export function ShapExplainer({ data }: { data: Explicacion }) {
  const max = Math.max(...data.top_shap.map((s) => Math.abs(s.contribucion)), 1e-9);

  return (
    <div>
      {data.top_shap.map((s) => {
        const positivo = s.contribucion >= 0;
        return (
          <div className="shap-row" key={s.feature}>
            <div className="shap-head">
              <span>{s.label}</span>
              <span className="contrib" style={{ color: positivo ? 'var(--rojo-fg)' : 'var(--azul)' }}>
                {positivo ? '+' : ''}
                {s.contribucion.toFixed(2)}
              </span>
            </div>
            <div className="shap-bar">
              <div
                style={{
                  width: `${(Math.abs(s.contribucion) / max) * 100}%`,
                  background: positivo ? 'var(--rojo)' : 'var(--azul)',
                }}
              />
            </div>
            <div className="shap-cmp">
              <span>
                hoy <b>{fmt(s.valor)}</b>
              </span>
              <span>
                su promedio <b>{fmt(s.promedio_personal)}</b>
              </span>
              <span>
                sus pares <b>{fmt(s.promedio_peer)}</b>
              </span>
            </div>
          </div>
        );
      })}
      <p className="hint">
        Contribución positiva (rojo) empuja hacia compromiso; negativa (azul) hacia comportamiento
        normal. La comparación contra su propio promedio y contra sus pares es lo que distingue una
        anomalía real de un usuario naturalmente intenso.
      </p>
    </div>
  );
}
