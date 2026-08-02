/** Layout y rutas. Cada vista se carga con lazy loading para no enviar todo el bundle de inicio. */
import { Suspense, lazy } from 'react';
import { NavLink, Navigate, Route, Routes } from 'react-router-dom';

import { Loading } from './components/ui';
import { AssistantWidget } from './features/assistant/AssistantWidget';
import { useHealth } from './hooks/useApi';

const TriagePage = lazy(() => import('./features/triage/TriagePage'));
const InvestigationPage = lazy(() => import('./features/investigation/InvestigationPage'));
const ExecutivePage = lazy(() => import('./features/executive/ExecutivePage'));

function EstadoBackend() {
  const { data, isError } = useHealth();
  if (isError) return <span className="status" style={{ color: 'var(--rojo-fg)' }}>backend no disponible</span>;
  if (!data) return <span className="status">conectando…</span>;
  return (
    <span className="status">
      periodo D{data.periodo_dias[0]}–D{data.periodo_dias[1]} · {data.usuarios.toLocaleString('es-MX')} usuarios
    </span>
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
