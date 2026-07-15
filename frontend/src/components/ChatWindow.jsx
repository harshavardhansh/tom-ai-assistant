import { useEffect, useRef, useState } from "react";
import Message from "./Message.jsx";
import Composer from "./Composer.jsx";
import { sendChat } from "../api/client.js";

const SESSION_ID = "web-" + Math.random().toString(36).slice(2, 9);

const EXAMPLES = [
  "List all L2 processes under Finance",
  "How many L3 processes are under Record to Report?",
  "Show the process flow for Procure to Pay",
  "What is the difference between tech-agnostic and tech-specific TOM?",
  "List the L1 processes under Finance and explain what a TOM is",
];

const BRAINS = [
  { cls: "graph", tag: "Graph", title: "Process hierarchy", desc: "Lists, counts, levels, roles, controls, and flows from the knowledge graph." },
  { cls: "vector", tag: "Documents", title: "Concepts & meaning", desc: "Definitions and leading practice, grounded in TOM documents with citations." },
  { cls: "multihop", tag: "Multi-hop", title: "Both at once", desc: "Compound questions decomposed, run in parallel, and synthesised together." },
];

// TOM chat personas from the approved L2 architecture ("TOM Chat Personas
// will be shown in UI Prompt").
const PERSONAS = [
  { id: "professional", label: "KPMG Professional", desc: "Engagement-ready answers for client work." },
  { id: "knowledge_manager", label: "Knowledge Manager", desc: "Provenance and content-gap detail for TOM curators." },
];

export default function ChatWindow({ getToken }) {
  const [messages, setMessages] = useState([]);
  const [loading, setLoading] = useState(false);
  const [persona, setPersona] = useState(PERSONAS[0].id);
  const endRef = useRef(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  async function ask(question) {
    setMessages((m) => [...m, { role: "user", text: question }]);
    setLoading(true);
    try {
      const res = await sendChat(question, SESSION_ID, getToken, persona);
      setMessages((m) => [...m, { role: "assistant", text: res.answer, response: res }]);
    } catch (e) {
      setMessages((m) => [
        ...m,
        { role: "assistant", text: "", error: e.message || "Something went wrong." },
      ]);
    } finally {
      setLoading(false);
    }
  }

  const empty = messages.length === 0;

  return (
    <div className="chat">
      <div className="transcript">
        {empty ? (
          <div className="welcome">
            <h1>Ask the Target Operating Model anything.</h1>
            <p>
              Plain-English answers about process structure and meaning across the
              TOM knowledge base — with citations, auto-generated diagrams, and
              one-click export to Word, PDF, or PowerPoint.
            </p>
            <div className="brains">
              {BRAINS.map((b) => (
                <div className={`brain ${b.cls}`} key={b.cls}>
                  <div className="tag">{b.tag}</div>
                  <h3>{b.title}</h3>
                  <p>{b.desc}</p>
                </div>
              ))}
            </div>
            <div className="examples">
              <h2>Try a question</h2>
              <div className="example-row">
                {EXAMPLES.map((q) => (
                  <button key={q} className="chip" onClick={() => ask(q)}>
                    {q}
                  </button>
                ))}
              </div>
            </div>
          </div>
        ) : (
          <div className="stream">
            {messages.map((msg, i) =>
              msg.error ? (
                <div className="msg assistant" key={i}>
                  <div className="avatar">TOM</div>
                  <div className="body">
                    <div className="error-note">{msg.error}</div>
                  </div>
                </div>
              ) : (
                <Message key={i} msg={msg} onAsk={ask} getToken={getToken} />
              )
            )}
            {loading && (
              <div className="msg assistant">
                <div className="avatar">TOM</div>
                <div className="body">
                  <div className="content">
                    <div className="typing">
                      <span /><span /><span />
                    </div>
                  </div>
                </div>
              </div>
            )}
            <div ref={endRef} />
          </div>
        )}
      </div>
      <div className="persona-bar" role="radiogroup" aria-label="Chat persona">
        <span className="persona-label">Persona</span>
        {PERSONAS.map((p) => (
          <button
            key={p.id}
            className={`persona-chip${persona === p.id ? " active" : ""}`}
            role="radio"
            aria-checked={persona === p.id}
            title={p.desc}
            onClick={() => setPersona(p.id)}
          >
            {p.label}
          </button>
        ))}
      </div>
      <Composer onSend={ask} disabled={loading} />
    </div>
  );
}
