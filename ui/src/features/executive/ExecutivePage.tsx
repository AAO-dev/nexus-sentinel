/**
 * Vista 3 — Panel ejecutivo (`/executive`, sección 8.2 del plan).
 *
 * Lo que resuelve: el CISO no hace triage; necesita tendencia de riesgo organizacional, qué rol
 * conductual concentra el riesgo, las cuentas de riesgo sostenido y la eficiencia del SOC para
 * justificar inversión. Los KPIs se muestran tal como los mide el backend, sin maquillaje.
 */
import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { Link } from 'react-router-dom';

import { ErrorState, KpiCard, Loading, RiskBadge, RiskValue } from '../../components/ui';
import { useOverview, useTriageQueue } from '../../hooks/useApi';

const CLUSTER_COLOR = ['#2a78d6', '#eda100', '#1baf7a', '#4a3aa7'];
const CLUSTER_NOMBRE: Record<number, string> = {
  0: 'Cuentas ligeras e intermitentes',
  1: 'Cuentas pesadas siempre encendidas',
};

export default function ExecutivePage() {
  const overview = useOverview();
  const top = useTriageQueue(undefined, 10);

  if (overview.isLoading) return <div className="page"><Loading rows={6} /></div>;
  if (overview.isError) return <div className="page"><ErrorState error={overview.error} /></div>;
  if (!overview.data) return null;

  const { tendencia, kpis_soc } = overview.data;
  // El contrato marca este campo como opcional: se normaliza a lista vacía en un solo punto.
  const tendencia_por_cluster = overview.data.tendencia_por_cluster ?? [];

  // Serie por día con una columna por cluster, para graficar la tendencia comparada.
  const clusters = [...new Set(tendencia_por_cluster.map((p) => p.peer_cluster))].sort();
  const porDia = tendencia.map((t) => {
    const fila: Record<string, number | string> = { dia: `D${t.day}` };
    for (const c of clusters) {
      const p = tendencia_por_cluster.find((x) => x.day === t.day && x.peer_cluster === c);
      if (p) fila[`c${c}`] = p.riesgo_medio;
    }
    return fila;
  });

  return (
    <div className="page">
      <h1>Panel ejecutivo</h1>
      <p className="sub">Riesgo organizacional, concentración por rol conductual y eficiencia del SOC.</p>

      <div className="grid grid-kpis" style={{ marginBottom: 20 }}>
        <KpiCard label="Riesgo organizacional" value={overview.data.riesgo_organizacional.toFixed(2)}
                 foot="Media 0-100 del periodo" />
        <KpiCard label="Alertas por día" value={kpis_soc?.alertas_por_dia ?? '—'}
                 foot={kpis_soc?.carga_revisable} />
        <KpiCard label="Casos rojos por día" value={kpis_soc?.casos_rojos_por_dia ?? '—'}
                 accent="var(--rojo-fg)" foot="Investigación prioritaria" />
        <KpiCard label="Cuentas comprometidas detectadas"
                 value={kpis_soc ? `${kpis_soc.cuentas_comprometidas_detectadas} / ${kpis_soc.cuentas_comprometidas_totales}` : '—'}
                 foot="Sobre el ground truth del periodo" />
      </div>

      <div className="grid grid-2">
        <div className="card">
          <h2>Tendencia de riesgo por rol conductual</h2>
          <ResponsiveContainer width="100%" height={260}>
            <LineChart data={porDia} margin={{ top: 8, right: 12, bottom: 4, left: -18 }}>
              <CartesianGrid stroke="#e1e0d9" strokeDasharray="3 3" vertical={false} />
              <XAxis dataKey="dia" tick={{ fontSize: 11, fill: '#898781' }} tickLine={false} axisLine={{ stroke: '#c3c2b7' }} />
              <YAxis tick={{ fontSize: 11, fill: '#898781' }} tickLine={false} axisLine={false} />
              <Tooltip contentStyle={{ fontSize: 12, borderRadius: 8, border: '1px solid #e1e0d9' }} />
              <Legend wrapperStyle={{ fontSize: 12 }} />
              {clusters.map((c, i) => (
                <Line key={c} type="monotone" dataKey={`c${c}`} name={CLUSTER_NOMBRE[c] ?? `Cluster ${c}`}
                      stroke={CLUSTER_COLOR[i % CLUSTER_COLOR.length]} strokeWidth={2} dot={false} />
              ))}
            </LineChart>
          </ResponsiveContainer>
          <p className="hint">
            Los roles no vienen de un organigrama (los datos están desidentificados): se descubren
            por comportamiento con KMeans. Sirven para saber qué perfil concentra el riesgo.
          </p>
        </div>

        <div className="card">
          <h2>Volumen de alertas por día</h2>
          <ResponsiveContainer width="100%" height={260}>
            <BarChart data={tendencia.map((t) => ({ dia: `D${t.day}`, alertas: t.alertas }))}
                      margin={{ top: 8, right: 12, bottom: 4, left: -18 }}>
              <CartesianGrid stroke="#e1e0d9" strokeDasharray="3 3" vertical={false} />
              <XAxis dataKey="dia" tick={{ fontSize: 11, fill: '#898781' }} tickLine={false} axisLine={{ stroke: '#c3c2b7' }} />
              <YAxis tick={{ fontSize: 11, fill: '#898781' }} tickLine={false} axisLine={false} />
              <Tooltip contentStyle={{ fontSize: 12, borderRadius: 8, border: '1px solid #e1e0d9' }} />
              <Bar dataKey="alertas" fill="#2a78d6" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
          <p className="hint">
            Los umbrales están calibrados a la capacidad operativa del SOC, no a números arbitrarios:
            el volumen diario debe caber en la jornada del equipo.
          </p>
        </div>
      </div>

      <div className="grid grid-2" style={{ marginTop: 16 }}>
        <div className="card">
          <h2>Cuentas de mayor riesgo</h2>
          {top.isLoading && <Loading />}
          {top.data && (
            <table>
              <thead>
                <tr><th>Usuario</th><th className="num">Riesgo</th><th>Nivel</th><th className="num">Días en alerta</th></tr>
              </thead>
              <tbody>
                {top.data.map((e) => (
                  <tr key={e.id}>
                    <td style={{ fontWeight: 600 }}>
                      <Link to={`/employee/${e.id}`} style={{ color: 'var(--azul)' }}>{e.id}</Link>
                    </td>
                    <td className="num"><RiskValue risk={e.risk_max} level={e.level} /></td>
                    <td><RiskBadge level={e.level} /></td>
                    <td className="num">{e.n_dias_alerta}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>

        <div className="card">
          <h2>Eficiencia del SOC</h2>
          {kpis_soc && (
            <table>
              <tbody>
                <tr style={{ cursor: 'default' }}>
                  <td>Tickets por día</td>
                  <td className="num" style={{ fontWeight: 700 }}>{kpis_soc.alertas_por_dia}</td>
                </tr>
                <tr style={{ cursor: 'default' }}>
                  <td>Falsos positivos</td>
                  <td className="num" style={{ fontWeight: 700, color: 'var(--rojo-fg)' }}>
                    {kpis_soc.pct_falsos_positivos}%
                  </td>
                </tr>
                <tr style={{ cursor: 'default' }}>
                  <td>Cobertura de cuentas comprometidas</td>
                  <td className="num" style={{ fontWeight: 700 }}>
                    {kpis_soc.cuentas_comprometidas_detectadas}/{kpis_soc.cuentas_comprometidas_totales}
                  </td>
                </tr>
                <tr style={{ cursor: 'default' }}>
                  <td>Tiempo medio de resolución</td>
                  <td className="num" style={{ color: 'var(--muted)' }}>
                    {kpis_soc.tiempo_resolucion_medio ?? 'sin datos'}
                  </td>
                </tr>
              </tbody>
            </table>
          )}
          <p className="hint">
            El tiempo de resolución requiere telemetría real de analistas usando el sistema; no se
            estima para no reportar un dato que no se midió. La tasa de falsos positivos se muestra
            sin filtrar: es el costo operativo real del umbral actual.
          </p>
        </div>
      </div>
    </div>
  );
}
