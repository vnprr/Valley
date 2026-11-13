import { ArrowUp, Loader2, X } from "lucide-react";
import { useState } from "react";
import { Orb } from "../ui/shaders";

export interface Reply {
  text: string;
  source: "ai" | "rules" | "error";
  warnings: string[];
  applied: string[]; // zapisane zmiany
  question: string | null; // pytanie doprecyzowujące
}

interface Props {
  busy: boolean;
  reply: Reply | null;
  showExamples: boolean;
  onSubmit: (text: string) => void;
  onDismiss: () => void;
}

const EXAMPLES = ["Dodaj Olę i Pawła", "Jadę rowerem, Ola samochodem, a dwie pozostałe osoby idą pieszo"];
const BADGE = { ai: "AI", rules: "BEZ AI", error: "BŁĄD" };

export function PromptBar({ busy, reply, showExamples, onSubmit, onDismiss }: Props) {
  const [text, setText] = useState("");
  const submit = (value: string) => {
    if (!value.trim() || busy) return;
    onSubmit(value.trim());
    setText("");
  };

  return (
    <div className="prompt-wrap">
      {reply && (
        <div className={`reply glass reply-${reply.question ? "question" : reply.source}`} role="status" data-source={reply.source}>
          <span className="reply-badge mono">{reply.question ? "PYTANIE" : BADGE[reply.source]}</span>
          <div>
            <p>{reply.text}</p>
            {reply.applied.length > 0 && <p className="applied mono">{reply.applied.join(" · ")}</p>}
            {reply.warnings.map((w) => <p className="warn" key={w}>{w}</p>)}
          </div>
          <button className="btn-icon" onClick={onDismiss} aria-label="Zamknij"><X size={14} /></button>
        </div>
      )}

      {showExamples && !reply && (
        <div className="examples">
          {EXAMPLES.map((e) => <button key={e} onClick={() => submit(e)}>{e}</button>)}
        </div>
      )}

      <form className={`prompt lens${busy ? " is-busy" : ""}`} onSubmit={(e) => { e.preventDefault(); submit(text); }}>
        <span className="prompt-orb" aria-hidden><Orb size={28} speed={busy ? 2.2 : 0.3} /></span>
        <input value={text} onChange={(e) => setText(e.target.value)} maxLength={500}
          placeholder="Opisz zmianę… np. „Usuń Adama i dodaj Kasię”" aria-label="Opisz spotkanie" />
        <button type="submit" disabled={busy || !text.trim()} aria-label="Wyślij">
          {busy ? <Loader2 size={18} className="spin" /> : <ArrowUp size={19} />}
        </button>
      </form>
    </div>
  );
}
