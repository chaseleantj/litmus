import { api } from "./api";
import { toErrorState, type ErrorState } from "./errors";
import { library } from "./library.svelte";
import type { MapResult } from "./types";

/**
 * Single owner of the map data and the map/axis sub-view. Module-level for
 * the same reason as compareState: the picture, the chosen sub-view and any
 * error survive the library sheet opening over the map or a trip to Detect.
 */
export const mapState = $state({
  data: null as MapResult | null,
  loading: false,
  error: null as ErrorState | null,
  view: "map" as "map" | "axis",
  /** The library signature the current data was computed for. */
  loadedFor: null as string | null,
  /** The signature a failed load was attempted for — auto-retry only fires
   *  again once the library actually changes; "Try again" always may. */
  erroredFor: null as string | null,
});

/**
 * What the map was built from. Any library mutation changes this, which is
 * how the map knows its picture is stale (ids + updated_at cover add, edit,
 * delete and import).
 */
export function librarySignature(): string {
  return library.examples.map((e) => `${e.id}:${e.updated_at}`).join("|");
}

let requestId = 0;

export async function loadMap(): Promise<void> {
  const signature = librarySignature();
  const id = ++requestId;
  mapState.loading = true;
  mapState.error = null;
  try {
    const data = await api.map();
    if (id !== requestId) return;
    mapState.data = data;
    mapState.loadedFor = signature;
    mapState.erroredFor = null;
  } catch (err) {
    if (id !== requestId) return;
    // A failed refresh keeps nothing: stale coordinates would silently lie
    // about a library that no longer exists.
    mapState.data = null;
    mapState.loadedFor = null;
    mapState.erroredFor = signature;
    mapState.error = toErrorState(err);
  } finally {
    if (id === requestId) mapState.loading = false;
  }
}
