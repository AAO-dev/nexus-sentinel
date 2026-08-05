/**
 * Apertura de la demostración.
 *
 * La página es apoyo visual, no guion: quien habla es el presentador. Cada elemento se limita a
 * una frase corta para que el público escuche en lugar de leer.
 */

export type Cifra = { valor: string; etiqueta: string; grave?: boolean };

export const CIFRAS: Cifra[] = [
  { valor: '40 M', etiqueta: 'tarjetas robadas', grave: true },
  { valor: '70 M', etiqueta: 'clientes afectados' },
  { valor: '3', etiqueta: 'semanas sin notarlo' },
  { valor: '200 MDD', etiqueta: 'en pérdidas', grave: true },
];

export const QUE_PASO: string[] = [
  'Robaron la cuenta de un proveedor',
  'Se pasearon como empleados más',
  'Llegaron a las cajas de las tiendas',
];

export const POR_QUE: string[] = [
  'Las alertas se perdieron entre miles',
  'Por separado, nada parecía sospechoso',
];

export type Usuario = { rol: string; recibe: string };

export const USUARIOS: Usuario[] = [
  { rol: 'Analista de seguridad', recibe: 'Una lista corta, ya justificada' },
  { rol: 'Director de seguridad', recibe: 'El riesgo del negocio, de un vistazo' },
  { rol: 'Auditoría', recibe: 'Cada decisión, registrada' },
];

export const MODELO: string[] = [
  'Banca, comercio y salud',
  'Suscripción anual por cuentas vigiladas',
  'Entra con una prueba de 30 días',
];

export type Cobertura = { casos: string; cobertura: string; pct: number };

export const COBERTURA: Cobertura[] = [
  { casos: '20 casos al día', cobertura: '31 %', pct: 31 },
  { casos: '100 casos al día', cobertura: '85 %', pct: 85 },
];
