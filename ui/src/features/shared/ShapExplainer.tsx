/**
 * Explicación SHAP del usuario-día.
 *
 * Invariante del sistema: ninguna puntuación se muestra sin su explicación. Cada contribución se
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
                este día <b>{fmt(s.valor)}</b>
              </span>
              <span>
                lo habitual en la cuenta <b>{fmt(s.promedio_personal)}</b>
              </span>
              <span>
                cuentas similares <b>{fmt(s.promedio_peer)}</b>
              </span>
            </div>
          </div>
        );
      })}
      <p className="hint">
        En rojo, lo que aumenta la sospecha; en azul, lo que la reduce. Comparar el día contra lo
        habitual de la cuenta y contra cuentas que se comportan parecido es lo que distingue algo
        realmente fuera de lugar de un usuario que sencillamente trabaja mucho.
      </p>
    </div>
  );
}
