import { Plus, Trash2 } from "lucide-react";
import { useEffect, useState } from "react";
import type { Health, Meeting, MeetingSummary } from "../api/types";

interface Props {
  meeting: Meeting | null;
  meetings: MeetingSummary[];
  health: Health | null;
  onOpen: (id: number) => void;
  onCreate: () => void;
  onDelete: () => void;
  onRename: (title: string) => void;
}

// Trzy osobne „wyspy” zamiast paska na całą szerokość: znak, sesja, stan usług.
// Mapa dostaje całą górę ekranu.
export function TopBar({ meeting, meetings, health, onOpen, onCreate, onDelete, onRename }: Props) {
  const [title, setTitle] = useState(meeting?.title ?? "");
  useEffect(() => setTitle(meeting?.title ?? ""), [meeting?.title]);

  return (
    <>
      <div className="brand">
        {/* Dwa koła, które się nakładają — wspólny grunt to ich część wspólna. */}
        <svg viewBox="0 0 44 28" width="44" height="28" aria-hidden>
          <circle cx="14" cy="14" r="12" fill="#ff6a3d" />
          <circle cx="30" cy="14" r="12" fill="#2fe3b4" style={{ mixBlendMode: "screen" }} />
          <path d="M22 4.1a12 12 0 0 1 0 19.8 12 12 0 0 1 0-19.8Z" fill="#fff7e6" />
        </svg>
        <h1>Common <em>Ground</em></h1>
      </div>

      <div className="session glass lens">
        <input className="title-input" value={title} maxLength={120} aria-label="Nazwa spotkania"
          onChange={(e) => setTitle(e.target.value)}
          onBlur={() => (title.trim() && title !== meeting?.title ? onRename(title.trim()) : setTitle(meeting?.title ?? ""))}
          onKeyDown={(e) => e.key === "Enter" && (e.target as HTMLInputElement).blur()} />
        <span className="session-tools">
          <select value={meeting?.id ?? ""} onChange={(e) => onOpen(Number(e.target.value))} aria-label="Zapisane spotkania">
            {meetings.map((m) => <option key={m.id} value={m.id}>{m.title}</option>)}
          </select>
          <button className="btn-icon" onClick={onCreate} title="Nowe spotkanie"><Plus size={16} /></button>
          <button className="btn-icon" onClick={onDelete} title="Usuń spotkanie"><Trash2 size={15} /></button>
        </span>
      </div>

      {health && (
        <div className="status glass mono">
          <span className="dot" /> trasy · {health.routing}
          <span className={`dot${health.ai === "openrouter" ? "" : " is-off"}`} />
          <span title={health.model ?? "brak klucza OpenRouter — tryb bez AI"}>{health.ai === "openrouter" ? "ai · openrouter" : "ai · reguły"}</span>
        </div>
      )}
    </>
  );
}
