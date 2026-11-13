import { Check, Crosshair, MapPin, Trash2, X } from "lucide-react";
import { useEffect, useState } from "react";
import type { Action, Participant } from "../api/types";
import { initialOf, type Tone } from "../status";
import { TRANSPORTS, transportInfo } from "../transport";

interface Props {
  participant: Participant;
  selected: boolean;
  picking: boolean;
  status: { text: string; tone: Tone };
  onSelect: () => void;
  onRun: (actions: Action[]) => void;
  onPickStart: () => void;
}

export function ParticipantCard({ participant: p, selected, picking, status, onSelect, onRun, onPickStart }: Props) {
  const [name, setName] = useState(p.name);
  const [limit, setLimit] = useState(p.max_minutes?.toString() ?? "");
  useEffect(() => setName(p.name), [p.name]);
  useEffect(() => setLimit(p.max_minutes?.toString() ?? ""), [p.max_minutes]);

  const update = (fields: Omit<Extract<Action, { type: "update_participant" }>, "type" | "ref">) =>
    onRun([{ type: "update_participant", ref: p.id, ...fields }]);
  const transport = transportInfo(p.transport);
  const transportIndex = TRANSPORTS.findIndex((t) => t.id === p.transport);

  const commitName = () => (name.trim() && name.trim() !== p.name ? update({ name: name.trim() }) : setName(p.name));
  const commitLimit = () => {
    const value = limit === "" ? null : Math.min(240, Math.max(5, Number(limit)));
    if (value === p.max_minutes) return setLimit(value?.toString() ?? "");
    if (value === null) onRun([{ type: "clear_participant_field", ref: p.id, field: "max_minutes" }]);
    else update({ max_minutes: value });
  };

  return (
    <article className={`card${selected ? " is-open" : ""}${picking ? " is-picking" : ""}`}
      style={{ "--c": p.color ?? "#ffc72e" } as React.CSSProperties} data-name={p.name}>
      <button className="card-head" onClick={onSelect} aria-expanded={selected}>
        <span className="card-dot" aria-hidden>{initialOf(p.name)}</span>
        <span className="card-text">
          <span className="card-name">{p.name}</span>
          <span className={`chip chip-${status.tone}`}>{status.text}</span>
        </span>
        {transport ? <transport.Icon size={17} className="card-icon" aria-label={transport.label} /> : <span className="card-icon muted">—</span>}
      </button>

      {p.start_proposal && (
        <div className="proposal">
          <MapPin size={14} />
          <span>Propozycja startu: <b>{p.start_proposal.label.split(",").slice(0, 2).join(",")}</b></span>
          <button className="btn-icon is-ok" title="Zatwierdź start" onClick={() => onRun([{ type: "confirm_start", ref: p.id }])}><Check size={14} /></button>
          <button className="btn-icon" title="Odrzuć" onClick={() => onRun([{ type: "clear_participant_field", ref: p.id, field: "start_proposal" }])}><X size={14} /></button>
        </div>
      )}

      {/* Zawsze w drzewie (płynne rozwijanie przez grid 0fr → 1fr); `inert` chowa pola przed fokusem. */}
      <div className="card-fold">
        <div className="card-body" {...({ inert: selected ? undefined : "" } as object)}>
          <label className="field">
            <span>Nazwa</span>
            <input value={name} maxLength={40} onChange={(e) => setName(e.target.value)} onBlur={commitName}
              onKeyDown={(e) => e.key === "Enter" && (e.target as HTMLInputElement).blur()} />
          </label>

          <div className="field">
            <span>Transport</span>
            <div className="segmented" style={{ "--i": Math.max(transportIndex, 0), "--has": transportIndex < 0 ? 0 : 1 } as React.CSSProperties}>
              {TRANSPORTS.map(({ id, label, Icon }) => (
                <button key={id} className={p.transport === id ? "is-on" : ""} onClick={() => update({ transport: id })} title={label}>
                  <Icon size={15} /> {label}
                </button>
              ))}
            </div>
          </div>

          <div className="field">
            <span>Start</span>
            <div className="start-row">
              <span className="mono start-value">
                {p.start ? <><MapPin size={13} /> {p.start.lat.toFixed(4)}, {p.start.lon.toFixed(4)}</> : <>nie ustawiono</>}
              </span>
              <button className={`btn-ghost${picking ? " is-on" : ""}`} onClick={onPickStart}>
                <Crosshair size={14} /> {picking ? "Kliknij mapę…" : "Ustaw start"}
              </button>
            </div>
          </div>

          <div className="card-foot">
            <label className="field field-inline">
              <span>Maks. czas</span>
              <input type="number" min={5} max={240} placeholder="—" value={limit}
                onChange={(e) => setLimit(e.target.value)} onBlur={commitLimit}
                onKeyDown={(e) => e.key === "Enter" && (e.target as HTMLInputElement).blur()} />
              <em>min</em>
            </label>
            <button className="btn-icon" onClick={() => onRun([{ type: "remove_participant", ref: p.id }])} title="Usuń osobę">
              <Trash2 size={14} />
            </button>
          </div>
        </div>
      </div>
    </article>
  );
}
