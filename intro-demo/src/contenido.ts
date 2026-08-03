/**
 * El caso Target 2013, separado de la presentación para que las cifras vivan en un solo lugar.
 * Las mismas que se narran en el guion de la demostración y en el documento final.
 */

export type Cifra = { valor: string; etiqueta: string; nota: string; grave?: boolean };

export const CIFRAS: Cifra[] = [
  { valor: '40 M', etiqueta: 'Tarjetas comprometidas', nota: 'Crédito y débito', grave: true },
  { valor: '70 M', etiqueta: 'Clientes afectados', nota: 'Datos personales expuestos' },
  { valor: '3', etiqueta: 'Semanas dentro de la red', nota: 'Sin ser detectados' },
  { valor: '+200 MDD', etiqueta: 'En pérdidas', nota: 'Sin contar el daño reputacional', grave: true },
];

export type Paso = { n: number; titulo: string; texto: string; resaltado?: string };

export const ANATOMIA: Paso[] = [
  {
    n: 1,
    titulo: 'Roban una credencial legítima',
    texto: 'Los atacantes no explotaron ninguna vulnerabilidad sofisticada. Comprometieron a un proveedor de aire acondicionado y se quedaron con su cuenta de acceso.',
    resaltado: 'La puerta se abrió con una llave válida.',
  },
  {
    n: 2,
    titulo: 'Se mueven lateralmente',
    texto: 'Con esa cuenta de mantenimiento recorrieron la red hasta alcanzar sistemas que un proveedor de climatización jamás tendría por qué tocar.',
    resaltado: 'Cada autenticación, por separado, era perfectamente válida.',
  },
  {
    n: 3,
    titulo: 'Llegan a las cajas registradoras',
    texto: 'Instalaron software malicioso en las terminales de punto de venta y capturaron los datos de cada tarjeta en el momento del pago.',
    resaltado: 'Tres semanas operando sin que nadie los detuviera.',
  },
];

export type Falla = { titulo: string; texto: string; respuesta: string };

export const FALLAS: Falla[] = [
  {
    titulo: 'Las alertas existían, pero nadie las investigó',
    texto: 'El sistema de seguridad sí generó avisos. Se ahogaron en un mar de alertas sin priorizar, y ninguna llegó a un analista con contexto suficiente para actuar.',
    respuesta: 'Una cola corta, ordenada por riesgo y con el motivo de cada caso en una línea.',
  },
  {
    titulo: 'La anomalía no estaba en ningún evento',
    texto: 'Ninguna autenticación individual era sospechosa. La señal estaba en el patrón: una cuenta tocando máquinas que nunca había visitado.',
    respuesta: 'Un modelo que no mira eventos sueltos, sino desviaciones respecto a la conducta habitual.',
  },
];
