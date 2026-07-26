/**
 * Componentes presentacionales compartidos: reciben datos por props y no hacen fetch.
 * Mantener la presentación separada del acceso a datos permite reutilizarlos entre las 3 vistas.
 */
import type { Nivel } from '../api/client';

export function RiskBadge({ level }: { level: Nivel }) {
  return <span className={`badge ${level}`}>{level}</span>;
}

/** El riesgo nunca se muestra solo: va con su nivel, para que el número tenga contexto. */
export function RiskValue({ risk, level }: { risk: number; level: Nivel }) {
  const color = level === 'rojo' ? 'var(--rojo-fg)' : level === 'naranja' ? 'var(--naranja-fg)' : 'var(--ink-2)';
  return (
    <span className="riskval" style={{ color }}>
      {risk.toFixed(1)}
    </span>
  );
}

export function KpiCard({
  label,
  value,
  foot,
  accent,
}: {
  label: string;
  value: string | number;
  foot?: string;
  accent?: string;
}) {
  return (
    <div className="card kpi">
      <div className="label">{label}</div>
      <div className="value" style={accent ? { color: accent } : undefined}>
        {value}
      </div>
      {foot && <div className="foot">{foot}</div>}
    </div>
  );
}

export function Loading({ rows = 4 }: { rows?: number }) {
  return (
    <div>
      {Array.from({ length: rows }, (_, i) => (
        <div key={i} className="skeleton" style={{ width: `${100 - i * 8}%` }} />
      ))}
    </div>
  );
}

/**
 * Estado de error legible. El 409 del backend no es un fallo: significa "día verde, registro
 * pasivo" — se muestra como información, no como alarma (coherente con el contrato de la Fase 6).
 */
export function ErrorState({ error }: { error: unknown }) {
  const status = (error as { status?: number })?.status;
  const detail = (error as { detail?: string })?.detail ?? 'No fue posible cargar los datos.';
  if (status === 409) return <div className="state">{detail}</div>;
  return <div className="state error">{detail}</div>;
}

export function Empty({ children }: { children: React.ReactNode }) {
  return <div className="state">{children}</div>;
}
