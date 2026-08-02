/**
 * Nombres de los perfiles de cuenta que se muestran en la interfaz.
 *
 * Los perfiles agrupan cuentas que se comportan parecido (cuántas máquinas tocan, con qué
 * volumen y en qué horario). Se nombran por su conducta observable porque los datos están
 * anonimizados y no existe un organigrama del que tomar el puesto real.
 */
const NOMBRES: Record<number, string> = {
  [-1]: 'Cuentas sin historial previo',
  0: 'Cuentas de uso ligero e intermitente',
  1: 'Cuentas de uso intensivo y continuo',
};

/** Forma corta, para encajar dentro de una frase sin repetir "cuentas". */
const DESCRIPCIONES: Record<number, string> = {
  [-1]: 'sin historial previo',
  0: 'uso ligero e intermitente',
  1: 'uso intensivo y continuo',
};

export const COLOR_PERFIL = ['#2a78d6', '#eda100', '#1baf7a', '#4a3aa7'];

export function nombrePerfil(perfil: number): string {
  return NOMBRES[perfil] ?? `Perfil ${perfil}`;
}

export function descripcionPerfil(perfil: number): string {
  return DESCRIPCIONES[perfil] ?? `perfil ${perfil}`;
}
