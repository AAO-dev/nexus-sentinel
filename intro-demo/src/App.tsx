/**
 * Apertura de la demostración: el precedente real del problema que resuelve Nexus Sentinel.
 * Página informativa; la herramienta en vivo se muestra después.
 */
import { ANATOMIA, CIFRAS, FALLAS, type Cifra, type Falla, type Paso } from './contenido';

function TarjetaCifra({ cifra }: { cifra: Cifra }) {
  return (
    <div className="cifra">
      <div className={`cifra-valor ${cifra.grave ? 'grave' : ''}`}>{cifra.valor}</div>
      <div className="cifra-etiqueta">{cifra.etiqueta}</div>
      <div className="cifra-nota">{cifra.nota}</div>
    </div>
  );
}

function PasoAtaque({ paso }: { paso: Paso }) {
  return (
    <li className="paso">
      <div className="paso-n">{paso.n}</div>
      <div>
        <h3>{paso.titulo}</h3>
        <p>{paso.texto}</p>
        {paso.resaltado && <p className="paso-clave">{paso.resaltado}</p>}
      </div>
    </li>
  );
}

function TarjetaFalla({ falla }: { falla: Falla }) {
  return (
    <div className="falla">
      <h3>{falla.titulo}</h3>
      <p>{falla.texto}</p>
      <div className="falla-respuesta">
        <span>Cómo lo resuelve Nexus Sentinel</span>
        <p>{falla.respuesta}</p>
      </div>
    </div>
  );
}

export default function App() {
  return (
    <div className="pagina">
      <header className="cabecera">
        <span className="etiqueta-caso">Caso real · Diciembre de 2013</span>
        <h1>
          Una de las brechas más costosas de la historia
          <br />
          <span>empezó con una credencial válida</span>
        </h1>
        <p className="entrada">
          Target, la segunda cadena minorista de Estados Unidos. Ningún exploit, ningún ataque de
          fuerza bruta: solo una cuenta legítima usada por quien no debía.
        </p>
      </header>

      <section className="cifras">
        {CIFRAS.map((c) => (
          <TarjetaCifra key={c.etiqueta} cifra={c} />
        ))}
      </section>

      <section className="bloque">
        <h2>Cómo ocurrió</h2>
        <ol className="anatomia">
          {ANATOMIA.map((p) => (
            <PasoAtaque key={p.n} paso={p} />
          ))}
        </ol>
      </section>

      <section className="bloque">
        <h2>Por qué nadie lo detuvo a tiempo</h2>
        <p className="bloque-entrada">
          El fallo no fue de tecnología, sino de atención y de enfoque. Dos problemas concretos, y
          ambos siguen vigentes hoy en la mayoría de las organizaciones.
        </p>
        <div className="fallas">
          {FALLAS.map((f) => (
            <TarjetaFalla key={f.titulo} falla={f} />
          ))}
        </div>
      </section>

      <footer className="puente">
        <img src="/logo.svg" alt="Nexus Sentinel" />
        <p>
          El uso indebido de credenciales no se ve en un evento. Se ve en el comportamiento.
          <br />
          <strong>Esto es lo que un analista habría visto ese día.</strong>
        </p>
      </footer>
    </div>
  );
}
