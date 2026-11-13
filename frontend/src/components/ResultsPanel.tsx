import { Building2, Mountain, RefreshCw } from "lucide-react";
import type { Meeting, PlaceScore } from "../api/types";
import type { ViewMode } from "../map/MapView";
import { Mesh } from "../ui/shaders";

interface Props {
  meeting: Meeting;
  alpha: number;
  mode: ViewMode;
  selectedPlaceId: string | null;
  onAlpha: (value: number) => void;
  onMode: (mode: ViewMode) => void;
  onSelectPlace: (id: string) => void;
}

export function ResultsPanel({ meeting, alpha, mode, selectedPlaceId, onAlpha, onMode, onSelectPlace }: Props) {
  const result = meeting.result;
  if (!result) return <Steps meeting={meeting} />;

  const rejected = result.candidates.filter((c) => !c.feasible).length;
  const selected = result.candidates.find((c) => c.place.id === selectedPlaceId);
  const selectedOutsideTop = selected && !result.recommendations.some((r) => r.place.id === selected.place.id);

  return (
    <section className={`panel glass panel-results${result.stale ? " is-stale" : ""}`}>
      <header className="panel-head">
        <h2>Rekomendacje</h2>
        <div className="toggle" role="tablist" style={{ "--i": mode === "city" ? 0 : 1 } as React.CSSProperties}>
          <button className={mode === "city" ? "is-on" : ""} onClick={() => onMode("city")}><Building2 size={14} /> CITY</button>
          <button className={mode === "valley" ? "is-on" : ""} onClick={() => onMode("valley")}><Mountain size={14} /> VALLEY</button>
        </div>
      </header>

      <div className="panel-body">
        {result.stale && (
          <p className="stale"><RefreshCw size={14} /> Uczestnicy się zmienili — wyniki są nieaktualne. Kliknij „Przelicz”.</p>
        )}

        <div className="alpha">
          <div className="alpha-labels mono"><span>szybkość</span><b>α {alpha.toFixed(2)}</b><span>sprawiedliwość</span></div>
          <input type="range" min={0} max={1} step={0.05} value={alpha} onChange={(e) => onAlpha(Number(e.target.value))}
            aria-label="Waga szybkość – sprawiedliwość" style={{ "--p": `${alpha * 100}%` } as React.CSSProperties} />
          <p className="formula mono">score = (1−α)·średnia + α·najdłuższy</p>
        </div>

        <ol className="recs">
          {result.recommendations.map((rec, i) => (
            <Recommendation key={rec.place.id} rank={i + 1} rec={rec} meeting={meeting}
              selected={rec.place.id === selectedPlaceId} onClick={() => onSelectPlace(rec.place.id)} />
          ))}
          {result.recommendations.length === 0 && <li className="empty">Żadne miejsce nie spełnia limitów czasu. Zwiększ limity lub zmień starty.</li>}
        </ol>

        {selectedOutsideTop && selected && (
          <div className="picked">
            <span className="mono">wybrany kandydat</span>
            <Recommendation rank={0} rec={selected} meeting={meeting} selected onClick={() => {}} />
          </div>
        )}

        <p className="summary">{result.summary}</p>
        {result.comment && <p className="ai-comment">{result.comment}</p>}

        {mode === "valley" && (
          <div className="legend">
            <div className="legend-bar" />
            <div className="mono legend-labels"><span>dno: najlepszy score</span><span>szczyt: najgorszy</span></div>
            <p>Dolina to wizualizacja przybliżona: wysokość w komórkach z kawiarnią to jej dokładny wynik, pomiędzy — interpolacja IDW. Obszary bez sprawdzonych kawiarni są puste. Ranking liczony jest wyłącznie z realnych czasów tras.</p>
          </div>
        )}

        <footer className="meta mono">
          {result.candidates.length} z {result.usage.pool_size} kawiarni · {rejected} odrzuconych · {result.provider.toUpperCase()}
          {" · "}{result.usage.credits} kr. · {(result.usage.duration_ms / 1000).toFixed(1)} s
        </footer>
      </div>
    </section>
  );
}

function Recommendation({ rank, rec, meeting, selected, onClick }: {
  rank: number; rec: PlaceScore; meeting: Meeting; selected: boolean; onClick: () => void;
}) {
  const worst = Math.max(...Object.values(rec.times_min).map((m) => m ?? 0), 1);
  const colors = meeting.participants.map((p) => p.color).filter((c): c is string => !!c);
  return (
    <li className={`rec${selected ? " is-selected" : ""}`} onClick={onClick}>
      {/* Wybrane miejsce „zlewa” kolory uczestników — wspólny grunt jako materiał. */}
      {selected && <span className="rec-mesh" aria-hidden><Mesh colors={colors} /></span>}
      <div className="rec-head">
        {rank > 0 && <span className="rec-rank">{rank}</span>}
        <div className="rec-title">
          <strong>{rec.place.name}</strong>
          {rec.place.address && <small>{rec.place.address}</small>}
        </div>
        <div className="rec-stats mono">
          <span><em>śr</em>{rec.mean_min?.toFixed(0) ?? "—"}′</span>
          <span><em>max</em>{rec.max_min?.toFixed(0) ?? "—"}′</span>
        </div>
      </div>
      <div className="rec-fold" aria-hidden={!selected}>
        <div className="bars">
          {meeting.participants.map((p) => {
            const m = rec.times_min[p.id];
            return (
              <div className="bar" key={p.id} style={{ "--c": p.color ?? "#ffc72e" } as React.CSSProperties}>
                <span className="bar-name">{p.name}</span>
                <span className="bar-track"><i style={{ width: `${((m ?? 0) / worst) * 100}%` }} /></span>
                <span className="mono bar-value">{m == null ? "—" : `${Math.round(m)} min`}</span>
              </div>
            );
          })}
          {rec.reason && <p className="reason">{rec.reason}</p>}
        </div>
      </div>
    </li>
  );
}

function Steps({ meeting }: { meeting: Meeting }) {
  const people = meeting.participants;
  const steps = [
    { done: people.length >= 2, text: "Opisz grupę albo dodaj osoby" },
    { done: people.length >= 2 && people.every((p) => p.start), text: "Wskaż punkty startowe na mapie" },
    { done: people.length >= 2 && people.every((p) => p.transport), text: "Wybierz środki transportu" },
    { done: false, text: "Znajdź najsprawiedliwsze miejsce" },
  ];
  return (
    <section className="panel glass panel-results panel-steps">
      <header className="panel-head"><h2>Plan</h2></header>
      <div className="panel-body">
        <ol className="steps">
          {steps.map((s, i) => (
            <li key={s.text} className={s.done ? "is-done" : ""}><span>{i + 1}</span>{s.text}</li>
          ))}
        </ol>
        <p className="hint">Python wybiera do 32 kandydatów z puli kawiarni, pobiera dla nich realne czasy dojazdu i wskazuje 3 najlepsze, oddalone od siebie miejsca. Tryb VALLEY pokazuje wynik jako dolinę 3D.</p>
      </div>
    </section>
  );
}
