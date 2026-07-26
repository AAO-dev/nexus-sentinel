/**
 * Vista 1 — Consola de triage (`/triage`, sección 8.2 del plan).
 *
 * Lo que resuelve: el analista SOC Tier 2 no necesita más alertas, necesita una cola corta,
 * priorizada y explicada. Aquí ve los KPIs, la cola ordenada por riesgo con el motivo en una línea,
 * y al seleccionar un usuario obtiene su evolución, la explicación SHAP del día y las acciones.
 */
import { useState } from 'react';
import { Link } from 'react-router-dom';

import type { Nivel } from '../../api/client';
import { Empty, ErrorState, KpiCard, Loading, RiskBadge, RiskValue } from '../../components/ui';
import { useEmployeeRisk, useExplanation, useOverview, useTriageQueue } from '../../hooks/useApi';
import { ActionBar } from '../shared/ActionBar';
import { RiskTimeline } from '../shared/RiskTimeline';
import { ShapExplainer } from '../shared/ShapExplainer';

const NIVELES: (Nivel | 'todos')[] = ['todos', 'rojo', 'naranja', 'verde'];

export default function TriagePage() {
  const [filtro, setFiltro] = useState<Nivel | 'todos'>('todos');
  const [sel, setSel] = useState<string | undefined>();
  const [dia, setDia] = useState<number | undefined>();

  const overview = useOverview();
  const cola = useTriageQueue(filtro === 'todos' ? undefined : filtro, 50);
  const serie = useEmployeeRisk(sel);
  const explicacion = useExplanation(sel, dia);

  // Al elegir un usuario se abre su día de mayor riesgo: el que motivó la alerta.
  function seleccionar(id: string, diaPico: number) {
    setSel(id);
    setDia(diaPico);
  }

  return (
    <div className="page">
      <h1>Consola de triage</h1>
      <p className="sub">
        Cola priorizada por riesgo de uso indebido de credenciales. Ninguna puntuación se muestra sin
        su explicación.
      </p>

      {overview.isLoading && <Loading rows={2} />}
      {overview.isError && <ErrorState error={overview.error} />}
      {overview.data && (
        <div className="grid grid-kpis" style={{ marginBottom: 20 }}>
          <KpiCard label="Alertas activas" value={overview.data.alertas_activas}
                   foot={`${overview.data.kpis_soc?.alertas_por_dia ?? '—'} por día`} />
          <KpiCard label="Casos rojos" value={overview.data.casos_rojos} accent="var(--rojo-fg)"
                   foot="Investigación prioritaria" />
          <KpiCard label="Riesgo organizacional" value={overview.data.riesgo_organizacional.toFixed(2)}
                   foot="Media 0-100 del periodo" />
          <KpiCard label="Usuarios monitoreados" value={overview.data.usuarios_monitoreados.toLocaleString('es-MX')} />
        </div>
      )}

      <div className="grid grid-2">
        <div className="card">
          <h2>Cola de triage</h2>
          <div className="filters">
            {NIVELES.map((n) => (
              <button key={n} className={`btn ${filtro === n ? 'on' : ''}`} onClick={() => setFiltro(n)}>
                {n === 'todos' ? 'Todos' : n}
              </button>
            ))}
          </div>

          {cola.isLoading && <Loading />}
          {cola.isError && <ErrorState error={cola.error} />}
          {cola.data?.length === 0 && <Empty>No hay usuarios en este nivel.</Empty>}
          {cola.data && cola.data.length > 0 && (
            <table>
              <thead>
                <tr>
                  <th>Usuario</th>
                  <th className="num">Riesgo</th>
                  <th>Nivel</th>
                  <th>Motivo principal</th>
                </tr>
              </thead>
              <tbody>
                {cola.data.map((e) => (
                  <tr key={e.id} className={sel === e.id ? 'sel' : ''}
                      onClick={() => seleccionar(e.id, e.dia_pico)}>
                    <td style={{ fontWeight: 600 }}>{e.id}</td>
                    <td className="num"><RiskValue risk={e.risk_max} level={e.level} /></td>
                    <td><RiskBadge level={e.level} /></td>
                    <td className="motivo">{e.motivo}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          <p className="hint">
            El riesgo mostrado es el máximo del periodo. Selecciona un usuario para ver su evolución
            y la explicación del día que disparó la alerta.
          </p>
        </div>

        <div style={{ display: 'grid', gap: 16 }}>
          <div className="card">
            <h2>Evolución del riesgo {sel ? `— ${sel}` : ''}</h2>
            {!sel && <Empty>Selecciona un usuario de la cola.</Empty>}
            {sel && serie.isLoading && <Loading rows={3} />}
            {sel && serie.isError && <ErrorState error={serie.error} />}
            {serie.data && <RiskTimeline serie={serie.data} selected={dia} onSelect={setDia} />}
            {serie.data && (
              <p className="hint">
                Cada punto es un usuario-día; el color indica su nivel. Haz clic en un punto para
                explicar ese día.
              </p>
            )}
          </div>

          <div className="card">
            <h2>Por qué el modelo lo señaló {dia !== undefined ? `— día ${dia}` : ''}</h2>
            {!sel && <Empty>Sin usuario seleccionado.</Empty>}
            {sel && explicacion.isLoading && <Loading rows={5} />}
            {sel && explicacion.isError && <ErrorState error={explicacion.error} />}
            {explicacion.data && (
              <>
                <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 14 }}>
                  <RiskValue risk={explicacion.data.risk} level={explicacion.data.level} />
                  <RiskBadge level={explicacion.data.level} />
                  <span className="motivo">{explicacion.data.motivo}</span>
                </div>
                <ShapExplainer data={explicacion.data} />
                {sel && dia !== undefined && (
                  <>
                    <hr style={{ border: 0, borderTop: '1px solid var(--line)', margin: '16px 0' }} />
                    <ActionBar employeeId={sel} day={dia} />
                    <p className="hint">
                      <Link to={`/employee/${sel}?date=${dia}`} style={{ color: 'var(--azul)', fontWeight: 600 }}>
                        Ver investigación completa →
                      </Link>
                    </p>
                  </>
                )}
              </>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
