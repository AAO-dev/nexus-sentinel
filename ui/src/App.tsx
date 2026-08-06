/** Layout y rutas. Cada vista se carga con lazy loading para no enviar todo el bundle de inicio. */
import { Suspense, lazy } from 'react';
import { NavLink, Navigate, Route, Routes } from 'react-router-dom';

import { Loading } from './components/ui';
import { AssistantWidget } from './features/assistant/AssistantWidget';
import { useEstadoBackend } from './hooks/useApi';

const TriagePage = lazy(() => import('./features/triage/TriagePage'));
const InvestigationPage = lazy(() => import('./features/investigation/InvestigationPage'));
const ExecutivePage = lazy(() => import('./features/executive/ExecutivePage'));

function EstadoBackend() {
  const { datos, despertando } = useEstadoBackend();
  if (despertando) return <span className="status">despertando el servicio…</span>;
  if (!datos) return <span className="status">conectando…</span>;
  return (
    <span className="status">
      periodo D{datos.periodo_dias[0]}–D{datos.periodo_dias[1]} · {datos.usuarios.toLocaleString('es-MX')} usuarios
    </span>
  );
}

/**
 * El backend vive en un plan gratuito que suspende el servicio por inactividad. Mientras arranca se
 * avisa de forma explícita, porque un error seco haría pensar que la aplicación está rota cuando en
 * realidad solo hay que esperar.
 */
function AvisoDespertando() {
  const { despertando } = useEstadoBackend();
  if (!despertando) return null;

  return (
    <div className="aviso" role="status">
      <span className="aviso-spinner" aria-hidden="true" />
      <span>
        <strong>Despertando el servicio…</strong> Está alojado en un plan gratuito que lo suspende
        tras un rato sin uso. La primera carga puede tardar hasta un minuto y los datos aparecerán
        solos, sin recargar. Si pasan más de dos minutos, actualiza la página.
      </span>
    </div>
  );
}

export default function App() {
  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          {/* El isotipo es decorativo: el nombre ya va en texto al lado, así que alt vacío
              evita que el lector de pantalla lo lea dos veces. */}
          <img src="/favicon.svg" alt="" className="brand-logo" />
          <span className="brand-text">Nexus <span>Sentinel</span></span>
        </div>
        <nav className="nav">
          <NavLink to="/triage" className={({ isActive }) => (isActive ? 'active' : '')}>Triage</NavLink>
          <NavLink to="/executive" className={({ isActive }) => (isActive ? 'active' : '')}>Ejecutivo</NavLink>
        </nav>
        <EstadoBackend />
      </header>

      <main>
        <AvisoDespertando />
        <Suspense fallback={<div className="page"><Loading rows={5} /></div>}>
          <Routes>
            <Route path="/" element={<Navigate to="/triage" replace />} />
            <Route path="/triage" element={<TriagePage />} />
            <Route path="/employee/:id" element={<InvestigationPage />} />
            <Route path="/executive" element={<ExecutivePage />} />
            <Route path="*" element={<div className="page"><h1>Página no encontrada</h1></div>} />
          </Routes>
        </Suspense>
      </main>

      <AssistantWidget />
    </div>
  );
}
