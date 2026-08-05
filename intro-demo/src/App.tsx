/**
 * Apertura de la demostración: el problema con un caso real, a quién le sirve la solución y
 * cómo se vende. Solo anclas visuales; el desarrollo lo pone la narración.
 */
import {
  CIFRAS,
  COBERTURA,
  MODELO,
  POR_QUE,
  QUE_PASO,
  USUARIOS,
  type Cifra,
  type Cobertura,
  type Usuario,
} from './contenido';

function TarjetaCifra({ cifra }: { cifra: Cifra }) {
  return (
    <div className="cifra">
      <div className={`cifra-valor ${cifra.grave ? 'grave' : ''}`}>{cifra.valor}</div>
      <div className="cifra-etiqueta">{cifra.etiqueta}</div>
    </div>
  );
}

function Paso({ n, texto }: { n: number; texto: string }) {
  return (
    <li className="paso">
      <span className="paso-n">{n}</span>
      <span>{texto}</span>
    </li>
  );
}

function TarjetaUsuario({ usuario }: { usuario: Usuario }) {
  return (
    <div className="usuario">
      <h3>{usuario.rol}</h3>
      <p>{usuario.recibe}</p>
    </div>
  );
}

function FilaCobertura({ fila }: { fila: Cobertura }) {
  return (
    <div className="cob">
      <div className="cob-cabeza">
        <span className="cob-casos">{fila.casos}</span>
        <span className="cob-valor">{fila.cobertura}</span>
      </div>
      <div className="cob-barra">
        <div className="cob-relleno" style={{ width: `${fila.pct}%` }} />
      </div>
    </div>
  );
}

export default function App() {
  return (
    <div className="pagina">
      {/* Portada del PDF. No se muestra en pantalla: la demostración arranca en el titular. */}
      <section className="portada">
        <img src="/logo.svg" alt="Nexus Sentinel" />
        <h1>Nexus Sentinel</h1>
        <p className="portada-sub">
          Detecta cuándo una cuenta legítima empieza a comportarse como no debería
        </p>
        <p className="portada-autor">
          Andre Arellano Ortiz
          <br />
          Diplomado en Ciencia de Datos · Generación 33 · UNAM
        </p>
      </section>

      <div className="hoja-apertura">
        <header className="cabecera">
          <span className="etiqueta-caso">Target · 2013</span>
          <h1>
            Entraron con una
            <br />
            <span>llave prestada</span>
          </h1>
        </header>

        <section className="cifras">
          {CIFRAS.map((c) => (
            <TarjetaCifra key={c.etiqueta} cifra={c} />
          ))}
        </section>
      </div>

      <section className="bloque">
        <h2>Qué pasó</h2>
        <ol className="pasos">
          {QUE_PASO.map((t, i) => (
            <Paso key={t} n={i + 1} texto={t} />
          ))}
        </ol>
      </section>

      <section className="bloque oscuro">
        <h2>Por qué nadie lo detuvo</h2>
        <ul className="fallas">
          {POR_QUE.map((t) => (
            <li key={t}>{t}</li>
          ))}
        </ul>
      </section>

      <section className="bloque">
        <h2>A quién le sirve</h2>
        <div className="usuarios">
          {USUARIOS.map((u) => (
            <TarjetaUsuario key={u.rol} usuario={u} />
          ))}
        </div>
      </section>

      <section className="bloque venta">
        <h2>Cómo se vende</h2>
        <ul className="modelo">
          {MODELO.map((t) => (
            <li key={t}>{t}</li>
          ))}
        </ul>
      </section>

      <section className="argumento">
        {COBERTURA.map((f) => (
          <FilaCobertura key={f.casos} fila={f} />
        ))}
        <p>Cuánta seguridad da contratar un analista más.</p>
      </section>

      <footer className="puente oscuro">
        <img src="/logo.svg" alt="Nexus Sentinel" />
        <p>Esto es lo que un analista habría visto ese día.</p>
      </footer>
    </div>
  );
}
