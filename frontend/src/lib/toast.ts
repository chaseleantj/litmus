import { get, writable } from "svelte/store";

export interface Toast {
  id: number;
  kind: "success" | "error";
  message: string;
}

export const toasts = writable<Toast[]>([]);

let nextId = 1;
const timers = new Map<number, ReturnType<typeof setTimeout>>();

export function toast(kind: Toast["kind"], message: string, durationMs = 4000): void {
  // The same notice again (e.g. deleting pairs one after another) restarts
  // the existing toast's clock instead of stacking duplicates.
  const existing = get(toasts).find((t) => t.kind === kind && t.message === message);
  if (existing) {
    clearTimeout(timers.get(existing.id));
    timers.set(
      existing.id,
      setTimeout(() => dismissToast(existing.id), durationMs),
    );
    return;
  }
  const id = nextId++;
  toasts.update((list) => [...list, { id, kind, message }]);
  timers.set(
    id,
    setTimeout(() => dismissToast(id), durationMs),
  );
}

export function dismissToast(id: number): void {
  clearTimeout(timers.get(id));
  timers.delete(id);
  toasts.update((list) => list.filter((t) => t.id !== id));
}
