/**
 * Mini-grafo ego usuario→computadoras: el elemento visual diferenciador del proyecto (v2).
 *
 * Dibuja las conexiones del día en disposición radial: en gris los destinos que el usuario ya
 * conocía, en rojo los que tocó por primera vez. Hace visible el movimiento lateral — el patrón
 * que ninguna alerta tradicional dispara porque cada autenticación individual es "válida".
 *
 * Los nodos vienen del backend (`ego_graph`); la UI solo los posiciona.
 */
import type { EgoGraph } from '../../api/client';

const SIZE = 300;
const CENTER = SIZE / 2;
const RADIO = 118;

export function EgoGraphMini({ ego, employeeId }: { ego: EgoGraph; employeeId: string }) {
  // Los nuevos se intercalan primero para que el patrón rojo sea legible aunque haya muchos nodos.
  const nodos = [
    ...ego.nodos_nuevos.map((n) => ({ id: n, nuevo: true })),
    ...ego.nodos_conocidos.map((n) => ({ id: n, nuevo: false })),
  ];
  const total = Math.max(nodos.length, 1);

  return (
    <div>
      <svg viewBox={`0 0 ${SIZE} ${SIZE}`} width="100%" style={{ maxWidth: SIZE }} role="img"
           aria-label={`Grafo de conexiones de ${employeeId}: ${ego.n_nuevos} destinos nuevos y ${ego.n_conocidos} conocidos`}>
        {nodos.map((n, i) => {
          const ang = (i / total) * 2 * Math.PI - Math.PI / 2;
          const x = CENTER + RADIO * Math.cos(ang);
          const y = CENTER + RADIO * Math.sin(ang);
          return (
            <g key={n.id}>
              <line x1={CENTER} y1={CENTER} x2={x} y2={y}
                    stroke={n.nuevo ? '#f3c9c5' : '#e1e0d9'} strokeWidth={n.nuevo ? 1.4 : 1} />
              <circle cx={x} cy={y} r={n.nuevo ? 5.5 : 4}
                      fill={n.nuevo ? '#e34948' : '#b8b6ae'} stroke="#fff" strokeWidth={1} />
            </g>
          );
        })}
        <circle cx={CENTER} cy={CENTER} r={17} fill="#2a78d6" stroke="#fff" strokeWidth={2} />
        <text x={CENTER} y={CENTER + 33} textAnchor="middle" fontSize={11} fontWeight={700} fill="#0b0b0b">
          {employeeId}
        </text>
      </svg>

      <div className="ego-legend">
        <span><i style={{ background: '#e34948' }} />{ego.n_nuevos} destinos nuevos</span>
        <span><i style={{ background: '#b8b6ae' }} />{ego.n_conocidos} ya conocidos</span>
      </div>
      <p className="hint">
        Histórico total del usuario: {ego.n_historicos_totales} destinos distintos.
        {ego.conocidos_truncados && ' La lista de conocidos se recortó para mantener el grafo legible.'}
      </p>
    </div>
  );
}

/** Lista de destinos con marca de "nuevo", complemento textual y accesible del grafo. */
export function DestinosChips({ ego }: { ego: EgoGraph }) {
  return (
    <div className="chips">
      {ego.nodos_nuevos.map((c) => (
        <span className="chip nuevo" key={c} title="Destino nunca antes visitado por este usuario">
          {c} · nuevo
        </span>
      ))}
      {ego.nodos_conocidos.map((c) => (
        <span className="chip" key={c}>{c}</span>
      ))}
    </div>
  );
}
