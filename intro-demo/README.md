# Apertura de la demostración — Nexus Sentinel

Página en **React + Vite** que presenta el problema de negocio antes de mostrar la consola. Sirve de
entrada a la demostración en vivo: primero el caso real que motiva el proyecto, a quién le sirve la
solución y cómo se vende; después, la herramienta funcionando.

De esta misma página sale el PDF de la presentación que se entrega en `docs/entregables/`.

## Ejecutar

```bash
npm install
```

```bash
npm run dev
```

Queda en **http://localhost:5174**, un puerto distinto al de la consola (5173) para poder tener
ambas abiertas durante la demostración.

Corre **solo en local**: no se despliega ni depende del backend, así que funciona aunque no haya
conexión o el servicio esté suspendido.

## Generar el PDF de la presentación

Con la página corriendo, desde el navegador: `Ctrl + P` → Destino **Guardar como PDF** → Márgenes
**Ninguno** → activar **Gráficos de fondo**.

Ese último ajuste importa: sin él, los bloques oscuros y el azul del argumento de venta salen en
blanco. La hoja de estilos de impresión convierte cada bloque en una diapositiva de 16:9.

## Estructura

```
src/
├── contenido.ts   # Todo el texto y las cifras, en un solo lugar
├── App.tsx        # Composición de las secciones
├── styles.css     # Estilos de pantalla y de impresión (@media print)
└── main.tsx       # Punto de entrada
public/            # Logotipo e icono, compartidos con la consola
```

Para cambiar una cifra o una frase basta con editar `contenido.ts`: los componentes recorren esos
datos y no llevan texto escrito dentro.

## Criterio de diseño

Es apoyo visual, no un documento. El texto se mantiene deliberadamente breve —frases de pocas
palabras, tipografía grande— para que el público escuche a quien presenta en lugar de ponerse a
leer. Los bloques alternan fondo claro y oscuro para dar ritmo al pasar de una sección a otra.

El lenguaje es de negocio, sin términos técnicos: el objetivo es que cualquiera entienda el problema
y la propuesta, sin saber de seguridad ni de datos.

Reutiliza la paleta y la tipografía de la consola para que la demostración se lea como una sola
pieza al pasar de esta página a la herramienta.
