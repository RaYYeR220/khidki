"use client";

import { useRef, useState } from "react";
import { api, ApiError, type Place } from "@/lib/api";
import s from "./app.module.css";

const SESSION_KEY = "khidki:chat-session";

function uuid4(): string {
  const c: Crypto = globalThis.crypto;
  if (typeof c.randomUUID === "function") return c.randomUUID();
  const b = c.getRandomValues(new Uint8Array(16));
  b[6] = (b[6] & 0x0f) | 0x40;
  b[8] = (b[8] & 0x3f) | 0x80;
  const h = [...b].map((x) => x.toString(16).padStart(2, "0")).join("");
  return `${h.slice(0, 8)}-${h.slice(8, 12)}-${h.slice(12, 16)}-${h.slice(16, 20)}-${h.slice(20)}`;
}

function getSession(): string {
  try {
    const v = localStorage.getItem(SESSION_KEY);
    if (v && /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(v)) return v;
    const n = uuid4();
    localStorage.setItem(SESSION_KEY, n);
    return n;
  } catch {
    return uuid4();
  }
}

interface Msg {
  who: "me" | "khidki" | "system";
  text: string;
  tools?: string[];
}

/** Paragraphs and **bold** only; everything else is shown as plain text. */
function Rich({ text }: { text: string }) {
  return (
    <>
      {text
        .split(/\n{2,}/)
        .filter((p) => p.trim())
        .map((p, i) => (
          <p key={i}>
            {p
              .split(/(\*\*[^*]+\*\*)/g)
              .map((part, j) =>
                part.startsWith("**") && part.endsWith("**") ? (
                  <strong key={j}>{part.slice(2, -2)}</strong>
                ) : (
                  <span key={j}>{part}</span>
                ),
              )}
          </p>
        ))}
    </>
  );
}

const SUGGEST = [
  "When should I walk tomorrow morning?",
  "Is it safe for my kids to play outside today?",
  "मुझे कल कब टहलना चाहिए?",
];

export default function ChatPanel({ place }: { place: Place | null }) {
  const [session] = useState(getSession);
  const [msgs, setMsgs] = useState<Msg[]>([]);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const logRef = useRef<HTMLDivElement>(null);

  function scrollDown() {
    requestAnimationFrame(() => {
      const el = logRef.current;
      if (el) el.scrollTop = el.scrollHeight;
    });
  }

  async function send(raw: string) {
    const t = raw.trim();
    if (!t || busy) return;
    setText("");
    setBusy(true);
    setMsgs((m) => [...m, { who: "me", text: t }]);
    scrollDown();
    try {
      const r = await api.chat({
        text: t,
        session,
        lat: place?.lat,
        lon: place?.lon,
        lang: /[ऀ-ॿ]/.test(t) ? "hi" : "en",
      });
      setMsgs((m) => [...m, { who: "khidki", text: r.reply, tools: r.tools }]);
    } catch (e) {
      const msg =
        e instanceof ApiError && e.status === 429
          ? "Too many messages from this connection. Wait a minute, then ask again."
          : e instanceof ApiError && e.status === 422
            ? "Khidki covers places in India only. Pick a place in India above."
            : "Khidki couldn't answer just now. Try again in a minute.";
      setMsgs((m) => [...m, { who: "system", text: msg }]);
    } finally {
      setBusy(false);
      scrollDown();
    }
  }

  return (
    <section className={`${s.card} ${s.chat}`} aria-labelledby="chat-h">
      <div className={s.chatHead}>
        <h2 className={s.cardT} id="chat-h">
          Ask Khidki
        </h2>
        <p className={s.cardP}>
          In English or Hindi. It answers from the same engine{place ? `, for ${place.name}` : ""}, and says when it doesn&apos;t
          know.
        </p>
      </div>

      <div className={s.log} ref={logRef} role="log" aria-live="polite" aria-label="Conversation">
        {msgs.length === 0 && (
          <div className={s.suggest}>
            {SUGGEST.map((q) => (
              <button key={q} type="button" onClick={() => send(q)} disabled={busy} lang={/[ऀ-ॿ]/.test(q) ? "hi" : undefined}>
                {q}
              </button>
            ))}
          </div>
        )}
        {msgs.map((m, i) => (
          <div key={i} className={m.who === "me" ? s.me : m.who === "khidki" ? s.bot : s.sys}>
            {m.who === "khidki" ? <Rich text={m.text} /> : <p>{m.text}</p>}
            {m.tools && m.tools.length > 0 && <p className={`${s.tools} mono`}>checked: {m.tools.join(", ")}</p>}
          </div>
        ))}
        {busy && <p className={s.typing}>Khidki is checking the monitors…</p>}
      </div>

      <form
        className={s.chatForm}
        onSubmit={(e) => {
          e.preventDefault();
          send(text);
        }}
      >
        <input
          className={s.input}
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder="When is the air cleanest for a run tomorrow?"
          aria-label="Your question"
          maxLength={1000}
        />
        <button className="btn btn-1 btn-sm" type="submit" disabled={busy || !text.trim()}>
          Ask
        </button>
      </form>
    </section>
  );
}
