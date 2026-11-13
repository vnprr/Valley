// Stan aplikacji w jednym miejscu. Każda zmiana to lista akcji wysłana do API
// (te same akcje wykonuje backend dla poleceń AI), a odpowiedź — pełne spotkanie —
// zastępuje stan lokalny. Spóźnione odpowiedzi są odrzucane (licznik `seq`).
import { Crosshair } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError, api } from "./api/client";
import type { Action, Health, Meeting, MeetingSummary, Point } from "./api/types";
import { ParticipantsPanel } from "./components/ParticipantsPanel";
import { PromptBar, type Reply } from "./components/PromptBar";
import { ResultsPanel } from "./components/ResultsPanel";
import { TopBar } from "./components/TopBar";
import { MapView, type ViewMode } from "./map/MapView";
import { LensDefs, usePointerLight } from "./ui/material";

export default function App() {
  const [meetings, setMeetings] = useState<MeetingSummary[]>([]);
  const [meeting, setMeeting] = useState<Meeting | null>(null);
  const [health, setHealth] = useState<Health | null>(null);
  const [selectedPid, setSelectedPid] = useState<string | null>(null);
  const [selectedPlaceId, setSelectedPlaceId] = useState<string | null>(null);
  const [mode, setMode] = useState<ViewMode>("city");
  const [picking, setPicking] = useState<string | null>(null);
  const [busy, setBusy] = useState<"interpret" | "solve" | null>(null);
  const [reply, setReply] = useState<Reply | null>(null);
  const [problems, setProblems] = useState<string[]>([]);
  const [alpha, setAlpha] = useState(0.5);
  const [tab, setTab] = useState<"people" | "results">("people"); // tylko telefon

  const queue = useRef(Promise.resolve()); // PATCH-e po kolei, w kolejności kliknięć
  const seq = useRef(0); // numer ostatniego żądania
  const activeId = useRef<number | null>(null);
  const alphaTimer = useRef<number>();

  const showError = (e: unknown) => {
    const err = e instanceof ApiError ? e : new ApiError(0, String(e));
    setReply({ text: err.message, source: "error", warnings: [], applied: [], question: null });
    // 404 na aktywnym spotkaniu = serwer go nie ma (np. efemeryczna baza podglądu na Vercelu
    // po recyklingu instancji). Zamiast martwego ekranu otwieramy pierwsze dostępne spotkanie.
    if (err.status === 404) {
      api.list().then(async (list) => {
        setMeetings(list);
        await open(list.length ? list[0].id : (await api.create()).id);
        setReply({ text: "To spotkanie nie istnieje już na serwerze — otwarto inne.", source: "error", warnings: [], applied: [], question: null });
      }).catch(() => {});
    }
  };

  const refreshList = useCallback(() => api.list().then(setMeetings).catch(() => {}), []);

  /** Wysyła żądanie i stosuje odpowiedź tylko, jeśli nadal dotyczy bieżącego stanu. */
  const track = useCallback(async <T,>(call: () => Promise<T>, meetingOf: (r: T) => Meeting) => {
    const mine = ++seq.current;
    const result = await call();
    const m = meetingOf(result);
    if (mine === seq.current && m.id === activeId.current) {
      setMeeting(m);
      return result;
    }
    // Spóźniona odpowiedź: nie nadpisujemy nią nowszego stanu, tylko dociągamy aktualny z bazy.
    if (m.id === activeId.current) {
      const fresh = await api.get(m.id);
      if (fresh.id === activeId.current) setMeeting(fresh);
    }
    return null;
  }, []);

  const open = useCallback(async (id: number) => {
    activeId.current = id;
    const m = await track(() => api.get(id), (r) => r);
    if (m) setAlpha(m.criteria.alpha);
    setSelectedPid(null);
    setPicking(null);
    setProblems([]);
    setReply(null);
  }, [track]);

  // Start: otwórz ostatnie spotkanie albo utwórz nowe (ref chroni przed StrictMode).
  const booted = useRef(false);
  useEffect(() => {
    if (booted.current) return;
    booted.current = true;
    api.health().then(setHealth).catch(() => {});
    (async () => {
      try {
        const list = await api.list();
        setMeetings(list);
        await open(list.length ? list[0].id : (await api.create()).id);
        if (!list.length) refreshList();
      } catch (e) {
        showError(e);
      }
    })();
  }, [open, refreshList]);

  // Wybrane miejsce: po nowym obliczeniu — zwycięzca; po zmianie α — zostaje, jeśli wciąż wykonalne.
  const result = meeting?.result ?? null;
  useEffect(() => {
    if (!result) return setSelectedPlaceId(null);
    setSelectedPlaceId((cur) =>
      cur && result.candidates.some((c) => c.place.id === cur && c.feasible) ? cur : result.recommendations[0]?.place.id ?? null,
    );
  }, [result]);
  useEffect(() => {
    if (result) setSelectedPlaceId(result.recommendations[0]?.place.id ?? null);
  }, [result?.computed_at]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setPicking(null);
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  /** Jedyna droga ręcznej zmiany: akcje -> PATCH -> zapisany stan z backendu. */
  const run = (actions: Action[], title?: string): Promise<Meeting | null> => {
    if (!meeting) return Promise.resolve(null);
    const id = meeting.id;
    const job = queue.current
      .then(() => track(() => api.update(id, { actions, title }), (r) => r))
      .catch((e) => { showError(e); return null; });
    queue.current = job.then(() => { refreshList(); });
    return job;
  };

  const addParticipant = async () => {
    const before = new Set(meeting?.participants.map((p) => p.id));
    const m = await run([{ type: "add_participant" }]);
    const added = m?.participants.find((p) => !before.has(p.id));
    if (added) setSelectedPid(added.id);
  };

  const pick = (point: Point) => {
    if (!picking || !meeting) return;
    run([{ type: "set_start", ref: picking, point }]);
    // Jeden klik = jeden punkt; po wyborze kursor wraca do normalnego.
    setSelectedPid(picking);
    setPicking(null);
  };

  const interpret = async (text: string) => {
    if (!meeting) return;
    setBusy("interpret");
    try {
      await queue.current;
      const out = await track(() => api.interpret(meeting.id, text), (r) => r.meeting);
      if (!out) return;
      setAlpha(out.meeting.criteria.alpha);
      setReply({ text: out.question ?? out.reply, source: out.source, warnings: out.warnings, applied: out.applied, question: out.question });
      const firstMissing = out.meeting.participants.find((p) => !p.start);
      if (firstMissing) setSelectedPid(firstMissing.id);
      setTab("people");
      refreshList();
    } catch (e) {
      showError(e);
    } finally {
      setBusy(null);
    }
  };

  const solve = async () => {
    if (!meeting) return;
    setBusy("solve");
    setProblems([]);
    setPicking(null);
    try {
      await queue.current;
      if (await track(() => api.solve(meeting.id), (r) => r)) {
        setTab("results");
        setReply(null);
      }
      refreshList();
    } catch (e) {
      if (e instanceof ApiError && e.problems.length) setProblems(e.problems);
      else showError(e);
    } finally {
      setBusy(null);
    }
  };

  const changeAlpha = (value: number) => {
    setAlpha(value);
    window.clearTimeout(alphaTimer.current);
    alphaTimer.current = window.setTimeout(() => run([{ type: "update_criteria", alpha: value }]), 140);
  };

  const createMeeting = async () => {
    try {
      const m = await api.create();
      await refreshList();
      await open(m.id);
    } catch (e) {
      showError(e);
    }
  };

  const deleteMeeting = async () => {
    if (!meeting || !window.confirm(`Usunąć spotkanie „${meeting.title}”?`)) return;
    await api.remove(meeting.id);
    const list = await api.list();
    setMeetings(list);
    if (list.length) await open(list[0].id);
    else await createMeeting();
  };

  const pickingName = meeting?.participants.find((p) => p.id === picking)?.name;

  usePointerLight();

  return (
    <div className={`app${busy === "solve" ? " is-solving" : ""}`}>
      <LensDefs />
      <MapView
        meetingId={meeting?.id ?? null}
        participants={meeting?.participants ?? []}
        result={result}
        selectedPid={selectedPid}
        selectedPlaceId={selectedPlaceId}
        mode={mode}
        picking={picking}
        onPick={pick}
        onSelectParticipant={(id) => { setSelectedPid(id); setTab("people"); }}
        onSelectPlace={(id) => { setSelectedPlaceId(id); setTab("results"); }}
        onMoveStart={(id, point) => run([{ type: "set_start", ref: id, point }])}
      />

      <TopBar meeting={meeting} meetings={meetings} health={health} onOpen={open} onCreate={createMeeting}
        onDelete={deleteMeeting} onRename={(title) => run([], title)} />

      {picking && (
        <div className="picking-banner glass lens">
          <Crosshair size={16} /> <span>Kliknij na mapie punkt startowy: <b>{pickingName}</b></span>
          <button className="kbd" onClick={() => setPicking(null)}>Esc</button>
        </div>
      )}

      {meeting && (
        <div className={`dock tab-${tab}`}>
          <nav className="dock-tabs mono" style={{ "--i": tab === "people" ? 0 : 1 } as React.CSSProperties}>
            <button className={tab === "people" ? "is-on" : ""} onClick={() => setTab("people")}>UCZESTNICY · {meeting.participants.length}</button>
            <button className={tab === "results" ? "is-on" : ""} onClick={() => setTab("results")}>WYNIKI{result ? ` · ${result.recommendations.length}` : ""}</button>
          </nav>
          <ParticipantsPanel
            meeting={meeting}
            selectedPid={selectedPid}
            selectedPlaceId={selectedPlaceId}
            picking={picking}
            solving={busy === "solve"}
            problems={problems}
            onSelect={(id) => setSelectedPid((cur) => (cur === id ? null : id))}
            onRun={run}
            onPickStart={(id) => { setSelectedPid(id); setPicking((cur) => (cur === id ? null : id)); }}
            onAdd={addParticipant}
            onSolve={solve}
          />
          <ResultsPanel meeting={meeting} alpha={alpha} mode={mode} selectedPlaceId={selectedPlaceId}
            onAlpha={changeAlpha} onMode={setMode} onSelectPlace={setSelectedPlaceId} />
        </div>
      )}

      <PromptBar busy={busy === "interpret"} reply={reply}
        showExamples={!!meeting && meeting.participants.length === 0}
        onSubmit={interpret} onDismiss={() => setReply(null)} />
    </div>
  );
}
