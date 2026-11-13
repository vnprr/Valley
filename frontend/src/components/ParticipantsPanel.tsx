import { ArrowRight, Loader2, Plus } from "lucide-react";
import { useState } from "react";
import type { Action, Meeting } from "../api/types";
import { cardStatus } from "../status";
import { Grain } from "../ui/shaders";
import { ParticipantCard } from "./ParticipantCard";

const MAX = 6;

interface Props {
  meeting: Meeting;
  selectedPid: string | null;
  selectedPlaceId: string | null;
  picking: string | null;
  solving: boolean;
  problems: string[];
  onSelect: (id: string) => void;
  onRun: (actions: Action[]) => void;
  onPickStart: (id: string) => void;
  onAdd: () => void;
  onSolve: () => void;
}

export function ParticipantsPanel(props: Props) {
  const { meeting, selectedPid, selectedPlaceId, picking, solving, problems } = props;
  const [hover, setHover] = useState(false);
  const people = meeting.participants;
  const result = meeting.result;
  const ready = people.length >= 2 && people.every((p) => p.start && p.transport);
  const label = solving ? "Liczę trasy…" : result?.stale ? "Przelicz" : result ? "Przelicz ponownie" : "Znajdź miejsce";

  return (
    <section className="panel glass panel-people">
      <header className="panel-head">
        <h2>Uczestnicy</h2>
        <span className="mono counter">{people.length}<i>/{MAX}</i></span>
      </header>

      <div className="cards">
        {people.length === 0 && (
          <p className="empty">Opisz grupę w polu na dole — np. <em>„Dodaj Olę i Pawła”</em> albo <em>„Będziemy we czwórkę”</em> — lub dodaj osoby ręcznie.</p>
        )}
        {people.map((p) => (
          <ParticipantCard
            key={p.id}
            participant={p}
            selected={p.id === selectedPid}
            picking={p.id === picking}
            status={cardStatus(p, result, selectedPlaceId)}
            onSelect={() => props.onSelect(p.id)}
            onRun={props.onRun}
            onPickStart={() => props.onPickStart(p.id)}
          />
        ))}
      </div>

      <button className="add" onClick={props.onAdd} disabled={people.length >= MAX}>
        <span><Plus size={14} /></span> Dodaj osobę
      </button>

      {problems.length > 0 && (
        <ul className="problems">{problems.map((p) => <li key={p}>{p}</li>)}</ul>
      )}

      <button className={`cta${solving ? " is-busy" : ""}`} onClick={props.onSolve} disabled={!ready || solving}
        onPointerEnter={() => setHover(true)} onPointerLeave={() => setHover(false)}>
        {ready && <span className="cta-shader" aria-hidden><Grain hot={hover || solving} /></span>}
        <span className="cta-label">{label}</span>
        {solving ? <Loader2 size={20} className="spin" /> : <ArrowRight size={20} className="cta-arrow" />}
      </button>
      {!ready && people.length > 0 && <p className="hint">Każda osoba potrzebuje startu i transportu (min. 2 osoby).</p>}
    </section>
  );
}
