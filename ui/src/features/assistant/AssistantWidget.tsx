/**
 * Asistente conversacional flotante (requerimiento del profesor).
 *
 * Adapta la técnica de function calling de los notebooks del profesor: el usuario pregunta en
 * lenguaje natural y el backend (DeepSeek) responde consultando los datos reales del modelo. Sirve
 * de guía (qué es el riesgo, cómo investigar) y de consulta (cuántas alertas, por qué se marcó a X).
 *
 * La API key vive solo en el backend; este widget solo habla con /assistant/chat.
 */
import { useEffect, useRef, useState } from 'react';
import { useMutation } from '@tanstack/react-query';

import { api, ApiError, type MensajeChat } from '../../api/client';
import { useAssistantHealth } from '../../hooks/useApi';

const SUGERENCIAS = [
  '¿Qué hace esta aplicación?',
  '¿Qué significa la puntuación de riesgo?',
  '¿Quiénes son los usuarios de mayor riesgo?',
  '¿Por qué se marcó a U-0737?',
];

const BIENVENIDA =
  'Hola, soy el asistente de Nexus Sentinel. Puedo explicarte cómo funciona la consola y sus ' +
  'conceptos, o responder preguntas sobre los datos del periodo analizado. ¿En qué te ayudo?';

export function AssistantWidget() {
  const [abierto, setAbierto] = useState(false);
  const [texto, setTexto] = useState('');
  const [historial, setHistorial] = useState<MensajeChat[]>([]);
  const finRef = useRef<HTMLDivElement>(null);
  const salud = useAssistantHealth();

  const enviar = useMutation({
    mutationFn: (mensajes: MensajeChat[]) => api.assistantChat(mensajes),
    onSuccess: (res) => setHistorial((h) => [...h, { role: 'assistant', content: res.reply }]),
  });

  useEffect(() => {
    finRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [historial, enviar.isPending]);

  function preguntar(pregunta: string) {
    const limpio = pregunta.trim();
    if (!limpio || enviar.isPending) return;
    const nuevos: MensajeChat[] = [...historial, { role: 'user', content: limpio }];
    setHistorial(nuevos);
    setTexto('');
    enviar.mutate(nuevos);
  }

  const noConfigurado = salud.data && !salud.data.disponible;

  return (
    <>
      <button className="fab" onClick={() => setAbierto((v) => !v)} aria-label="Abrir asistente">
        {abierto ? '×' : '💬'}
      </button>

      {abierto && (
        <div className="chat" role="dialog" aria-label="Asistente de Nexus Sentinel">
          <div className="chat-head">
            <strong>Asistente</strong>
            <span>{salud.data?.disponible ? salud.data.modelo : 'guía'}</span>
          </div>

          <div className="chat-body">
            <div className="msg bot">{BIENVENIDA}</div>

            {historial.length === 0 && (
              <div className="chat-sugerencias">
                {SUGERENCIAS.map((s) => (
                  <button key={s} className="btn" onClick={() => preguntar(s)} disabled={noConfigurado}>
                    {s}
                  </button>
                ))}
              </div>
            )}

            {historial.map((m, i) => (
              <div key={i} className={`msg ${m.role === 'user' ? 'user' : 'bot'}`}>
                {m.content}
              </div>
            ))}

            {enviar.isPending && <div className="msg bot pensando">escribiendo…</div>}
            {enviar.isError && (
              <div className="msg bot err">
                {enviar.error instanceof ApiError && enviar.error.status === 503
                  ? 'El asistente no está configurado en este despliegue (falta la API key de DeepSeek en el backend).'
                  : 'No pude responder ahora mismo. Intenta de nuevo.'}
              </div>
            )}
            <div ref={finRef} />
          </div>

          <form
            className="chat-input"
            onSubmit={(e) => {
              e.preventDefault();
              preguntar(texto);
            }}
          >
            <input
              value={texto}
              onChange={(e) => setTexto(e.target.value)}
              placeholder={noConfigurado ? 'Asistente no configurado' : 'Escribe tu pregunta…'}
              maxLength={2000}
              disabled={noConfigurado}
            />
            <button className="btn on" type="submit" disabled={enviar.isPending || noConfigurado || !texto.trim()}>
              Enviar
            </button>
          </form>
        </div>
      )}
    </>
  );
}
