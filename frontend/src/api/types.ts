// Typy lustrzane do schematów Pydantic w backend/app/schemas.

export type Transport = "walk" | "bike" | "car";

export interface Point {
  lat: number;
  lon: number;
}

export interface StartProposal extends Point {
  label: string;
}

export interface Participant {
  id: string;
  name: string;
  color: string | null;
  transport: Transport | null;
  start: Point | null;
  start_proposal: StartProposal | null; // z geokodera — czeka na zatwierdzenie
  max_minutes: number | null;
}

// Te same akcje wysyła UI (PATCH) i zwraca AI — backend wykonuje je jednym executorem.
export type Action =
  | { type: "add_participant"; name?: string }
  | { type: "update_participant"; ref: string; name?: string; transport?: Transport; max_minutes?: number }
  | { type: "clear_participant_field"; ref: string; field: "transport" | "max_minutes" | "start" | "start_proposal" }
  | { type: "remove_participant"; ref: string }
  | { type: "set_start"; ref: string; point: Point }
  | { type: "confirm_start"; ref: string }
  | { type: "update_criteria"; alpha: number };

export interface Usage {
  places_requests: number;
  matrix_requests: number;
  matrix_cells: number;
  reused_cells: number;
  credits: number;
  pool_size: number;
  duration_ms: number;
}

export interface Place {
  id: string;
  name: string;
  lat: number;
  lon: number;
  address: string | null;
}

export interface PlaceScore {
  place: Place;
  times_min: Record<string, number | null>;
  mean_min: number | null;
  max_min: number | null;
  score: number | null;
  feasible: boolean;
  reason: string | null;
}

export interface Result {
  stale: boolean;
  provider: string;
  computed_at: string;
  alpha: number;
  recommendations: PlaceScore[];
  candidates: PlaceScore[];
  surface: GeoJSON.FeatureCollection & { min?: number; max?: number };
  summary: string;
  comment: string | null;
  usage: Usage;
}

export interface Meeting {
  id: number;
  title: string;
  participants: Participant[];
  criteria: { alpha: number };
  result: Result | null;
  created_at: string;
  updated_at: string;
}

export interface MeetingSummary {
  id: number;
  title: string;
  participant_count: number;
  has_analysis: boolean;
  updated_at: string;
}

export interface InterpretOut {
  meeting: Meeting;
  reply: string;
  applied: string[]; // co faktycznie zapisano
  question: string | null; // niejednoznaczne polecenie — nic nie zmieniono
  warnings: string[];
  source: "ai" | "rules";
}

export interface Health {
  status: string;
  routing: "geoapify" | "osrm";
  ai: "openrouter" | "rules";
  model: string | null;
}
