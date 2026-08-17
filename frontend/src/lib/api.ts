import { writable } from "svelte/store";
import { ApiError } from "./errors";
import type {
  CompareResult,
  Example,
  ImportResult,
  MapResult,
  PairInput,
  ScoreResult,
} from "./types";

export { ApiError };

/** True once the DEV mock has taken over because the real API was unreachable. */
export const mockActive = writable(false);
let mockOn = false;

type MockHandler = (method: string, path: string, body: unknown) => Promise<unknown>;
let mockHandler: MockHandler | null = null;

async function getMock(): Promise<MockHandler> {
  if (!mockHandler) {
    const mod = await import("./mock");
    mockHandler = mod.handle;
  }
  mockOn = true;
  mockActive.set(true);
  return mockHandler;
}

/**
 * The message to show for a failed response. FastAPI reports its own errors as
 * a `detail` string, but validation failures arrive as a list of field errors —
 * without this they would all surface as "Request failed (422)".
 */
async function errorDetail(res: Response): Promise<string> {
  try {
    const detail = (await res.json())?.detail;
    if (typeof detail === "string") return detail;
    const first = Array.isArray(detail) ? detail[0] : null;
    if (typeof first?.msg === "string") {
      const msg = first.msg.replace(/^Value error, /, "");
      // Field errors name the field ("ai", "text"); whole-body errors don't.
      const field = first.loc?.[first.loc.length - 1];
      return typeof field === "string" && field !== "body"
        ? `The "${field}" field ${msg}.`
        : msg[0].toUpperCase() + msg.slice(1) + ".";
    }
  } catch {
    /* non-JSON error body; fall through to the generic message */
  }
  return `Request failed (${res.status})`;
}

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  // Once the mock is active in dev, stay on it for the session so state is coherent.
  if (import.meta.env.DEV && mockOn) {
    return (await getMock())(method, path, body) as Promise<T>;
  }

  let res: Response;
  try {
    res = await fetch(path, {
      method,
      headers: body !== undefined ? { "Content-Type": "application/json" } : undefined,
      body: body !== undefined ? JSON.stringify(body) : undefined,
    });
  } catch (err) {
    // Network-level failure: in dev, fall back to the in-memory mock backend.
    if (import.meta.env.DEV) {
      return (await getMock())(method, path, body) as Promise<T>;
    }
    throw new ApiError(0, "Cannot reach the server. Check your connection and try again.");
  }

  // Vite's dev proxy returns 500 with a plain-text body when the target is down.
  if (import.meta.env.DEV && res.status >= 500) {
    const clone = res.clone();
    try {
      await clone.json();
    } catch {
      return (await getMock())(method, path, body) as Promise<T>;
    }
  }

  if (!res.ok) {
    throw new ApiError(res.status, await errorDetail(res));
  }

  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

export const api = {
  listExamples: () => request<Example[]>("GET", "/api/examples"),
  createExample: (pair: PairInput) => request<Example>("POST", "/api/examples", pair),
  updateExample: (id: number, pair: PairInput) =>
    request<Example>("PUT", `/api/examples/${id}`, pair),
  deleteExample: (id: number) => request<void>("DELETE", `/api/examples/${id}`),
  importExamples: (pairs: PairInput[]) =>
    request<ImportResult>("POST", "/api/examples/import", pairs),
  compare: (first: string, second: string) =>
    request<CompareResult>("POST", "/api/compare", { first, second }),
  score: (text: string) => request<ScoreResult>("POST", "/api/score", { text }),
  map: () => request<MapResult>("GET", "/api/map"),
};
