/**
 * Evolución del riesgo con los umbrales operativos sombreados.
 * Los umbrales vienen del backend vía los niveles de cada punto: la UI no los recalcula.
 */
import {
  CartesianGrid,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';

import type { SerieRiesgo } from '../../api/client';

const COLOR: Record<string, string> = {
  verde: '#1b5e20',
  naranja: '#a34e00',
  rojo: '#e34948',
};

export function RiskTimeline({
  serie,
  selected,
  onSelect,
}: {
  serie: SerieRiesgo;
  selected?: number;
  onSelect?: (day: number) => void;
}) {
  const data = serie.timeline.map((p) => ({ ...p, dia: `D${p.day}` }));
  // Umbral naranja aproximado: el menor riesgo entre los días que el backend marcó como alerta.
  const alertas = serie.timeline.filter((p) => p.level !== 'verde').map((p) => p.risk);
  const umbral = alertas.length ? Math.min(...alertas) : undefined;

  return (
    <ResponsiveContainer width="100%" height={230}>
      <LineChart
        data={data}
        margin={{ top: 8, right: 12, bottom: 4, left: -18 }}
        onClick={(e) => {
          const p = e?.activePayload?.[0]?.payload as { day: number } | undefined;
          if (p && onSelect) onSelect(p.day);
        }}
      >
        <CartesianGrid stroke="#e1e0d9" strokeDasharray="3 3" vertical={false} />
        <XAxis dataKey="dia" tick={{ fontSize: 11, fill: '#898781' }} tickLine={false} axisLine={{ stroke: '#c3c2b7' }} />
        <YAxis tick={{ fontSize: 11, fill: '#898781' }} tickLine={false} axisLine={false} domain={[0, 100]} />
        <Tooltip
          contentStyle={{ fontSize: 12, borderRadius: 8, border: '1px solid #e1e0d9' }}
          formatter={(v: number) => [v.toFixed(1), 'riesgo']}
        />
        {umbral !== undefined && (
          <ReferenceLine
            y={umbral}
            stroke="#a34e00"
            strokeDasharray="4 4"
            label={{ value: 'umbral de alerta', fontSize: 10, fill: '#a34e00', position: 'insideTopRight' }}
          />
        )}
        <Line
          type="monotone"
          dataKey="risk"
          stroke="#2a78d6"
          strokeWidth={2}
          dot={(props: { cx?: number; cy?: number; payload?: { level: string; day: number } }) => {
            const { cx, cy, payload } = props;
            if (cx === undefined || cy === undefined || !payload) return <g key="none" />;
            const activo = payload.day === selected;
            return (
              <circle
                key={payload.day}
                cx={cx}
                cy={cy}
                r={activo ? 6 : 4}
                fill={COLOR[payload.level] ?? '#2a78d6'}
                stroke="#fff"
                strokeWidth={activo ? 2 : 1}
              />
            );
          }}
        />
      </LineChart>
    </ResponsiveContainer>
  );
}
