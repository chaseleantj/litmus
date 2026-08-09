import { writable } from "svelte/store";

export interface Toast {
  id: number;
  kind: "success" | "error";
  message: string;
}

export const toasts = writable<Toast[]>([]);

let nextId = 1;

export function toast(kind: Toast["kind"], message: string, durationMs = 4000): void {
  const id = nextId++;
  toasts.update((list) => [...list, { id, kind, message }]);
  setTimeout(() => dismissToast(id), durationMs);
}

export function dismissToast(id: number): void {
  toasts.update((list) => list.filter((t) => t.id !== id));
}
