// Cienka warstwa nad fetch: jedna funkcja na endpoint, błędy jako ApiError.
import type { Action, Health, InterpretOut, Meeting, MeetingSummary } from "./types";

export class ApiError extends Error {
  constructor(public status: number, message: string, public problems: string[] = []) {
    super(message);
  }
}

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  let response: Response;
  try {
    response = await fetch(path, {
      method,
      headers: body ? { "Content-Type": "application/json" } : undefined,
      body: body ? JSON.stringify(body) : undefined,
    });
  } catch {
    throw new ApiError(0, "Brak połączenia z backendem (czy działa uvicorn na :8000?)");
  }
  if (response.status === 204) return undefined as T;
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    // FastAPI zwraca przy 422 listę błędów walidacji Pydantic — skleimy ich komunikaty.
    const detail = typeof data.detail === "string" ? data.detail
      : Array.isArray(data.detail) ? data.detail.map((d: { msg: string }) => d.msg).join("; ")
      : "Niepoprawne dane";
    throw new ApiError(response.status, detail, data.problems ?? []);
  }
  return data as T;
}

export const api = {
  health: () => request<Health>("GET", "/api/health"),
  list: () => request<MeetingSummary[]>("GET", "/api/meetings"),
  create: (title = "Nowe spotkanie") => request<Meeting>("POST", "/api/meetings", { title }),
  get: (id: number) => request<Meeting>("GET", `/api/meetings/${id}`),
  remove: (id: number) => request<void>("DELETE", `/api/meetings/${id}`),
  update: (id: number, patch: { title?: string; actions?: Action[] }) =>
    request<Meeting>("PATCH", `/api/meetings/${id}`, patch),
  interpret: (id: number, text: string) => request<InterpretOut>("POST", `/api/meetings/${id}/interpret`, { text }),
  solve: (id: number) => request<Meeting>("POST", `/api/meetings/${id}/solve`),
};
