/**
 * Vista 2 — Investigación (`/employee/:id`).
 *
 * Lo que resuelve: cuando el analista decide profundizar, necesita ver la actividad del día, cómo
 * se compara contra la actividad habitual de esa cuenta y contra cuentas similares, y sobre todo
 * el mapa de conexiones que hace visible el movimiento lateral. Aquí también queda el historial
 * de decisiones.
 */
import { useSearchParams, useParams, Link } from 'react-router-dom';

import { Empty, ErrorState, KpiCard, Loading, RiskBadge, RiskValue } from '../../components/ui';
import { useActivity, useEmployeeRisk, useExplanation } from '../../hooks/useApi';
import { ActionBar } from '../shared/ActionBar';
import { descripcionPerfil } from '../shared/perfiles';
import { RiskTimeline } from '../shared/RiskTimeline';
import { ShapExplainer } from '../shared/ShapExplainer';
import { DestinosChips, EgoGraphMini } from './EgoGraphMini';

export default function InvestigationPage() {
  const { id = '' } = useParams();
  const [params, setParams] = useSearchParams();
  const serie = useEmployeeRisk(id);

  // Día a investigar: el de la URL, o el de mayor riesgo del usuario.
  const diaUrl = params.get('date');
  const diaPico = serie.data?.timeline.reduce(
    (mejor, p) => (mejor && mejor.risk >= p.risk ? mejor : p),
    serie.data.timeline[0],
  );
  const dia = diaUrl ? Number(diaUrl) : diaPico?.day;

  const actividad = useActivity(id, dia);
  const explicacion = useExplanation(id, dia);

  const seleccionarDia = (d: number) => setParams({ date: String(d) }, { replace: true });

  return (
    <div className="page">
      <p className="sub" style={{ marginBottom: 6 }}>
        <Link to="/triage" style={{ color: 'var(--azul)', fontWeight: 600 }}>← Volver al triage</Link>
      </p>
      <h1>Investigación — {id}</h1>
      <p className="sub">
        Actividad de autenticación, comparación contra su actividad habitual y mapa de conexiones
        {dia !== undefined ? ` · día ${dia}` : ''}.
      </p>

      {serie.isLoading && <Loading rows={3} />}
      {serie.isError && <ErrorState error={serie.error} />}

      {actividad.data && (
        <div className="grid grid-kpis" style={{ marginBottom: 20 }}>
          <KpiCard label="Eventos de auth" value={actividad.data.n_eventos.toLocaleString('es-MX')} />
          <KpiCard label="Computadoras destino" value={actividad.data.n_dst}
                   foot={`${actividad.data.n_destinos_nuevos} nunca antes vistas`}
                   accent={actividad.data.n_destinos_nuevos > 0 ? 'var(--rojo-fg)' : undefined} />
          <KpiCard label="Máquinas origen nuevas" value={actividad.data.n_origenes_nuevos} />
          <KpiCard label="Ratio NTLM" value={`${(actividad.data.ratio_ntlm * 100).toFixed(1)}%`}
                   foot="Protocolo legado (pass-the-hash)" />
          <KpiCard label="Fallos" value={actividad.data.n_fallos} />
          <KpiCard label="Fuera de horario" value={actividad.data.n_fuera_horario}
                   foot="Horario laboral 7:00–16:00" />
        </div>
      )}

      <div className="grid grid-2">
        <div className="card">
          <h2>Mapa de conexiones del día</h2>
          {!dia && <Empty>Sin día seleccionado.</Empty>}
          {dia !== undefined && actividad.isLoading && <Loading rows={4} />}
          {dia !== undefined && actividad.isError && <ErrorState error={actividad.error} />}
          {actividad.data?.ego_graph ? (
            <div className="ego">
              <div className="ego-panel">
                <EgoGraphMini ego={actividad.data.ego_graph} employeeId={id} />
              </div>
              <div className="ego-panel">
                <h3>Destinos alcanzados</h3>
                <DestinosChips ego={actividad.data.ego_graph} />
              </div>
            </div>
          ) : (
            actividad.data && <Empty>Sin datos de grafo para este día.</Empty>
          )}
          <p className="hint">
            El movimiento lateral no se ve en eventos sueltos —cada autenticación es válida— sino en
            el patrón: destinos que esta cuenta jamás había tocado apareciendo de golpe.
          </p>
        </div>

        <div style={{ display: 'grid', gap: 16 }}>
          <div className="card">
            <h2>Evolución del riesgo</h2>
            {serie.data && <RiskTimeline serie={serie.data} selected={dia} onSelect={seleccionarDia} />}
            {serie.data && (
              <p className="hint">
                Perfil de la cuenta: {descripcionPerfil(serie.data.peer_cluster)}. Haz clic en un
                punto para cambiar el día investigado.
              </p>
            )}
          </div>

          <div className="card">
            <h2>Qué se salió de lo normal</h2>
            {dia !== undefined && explicacion.isLoading && <Loading rows={4} />}
            {dia !== undefined && explicacion.isError && <ErrorState error={explicacion.error} />}
            {explicacion.data && (
              <>
                <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 14 }}>
                  <RiskValue risk={explicacion.data.risk} level={explicacion.data.level} />
                  <RiskBadge level={explicacion.data.level} />
                </div>
                <ShapExplainer data={explicacion.data} />
              </>
            )}
          </div>

          {dia !== undefined && (
            <div className="card">
              <h2>Decisión del analista</h2>
              <ActionBar employeeId={id} day={dia} />
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
