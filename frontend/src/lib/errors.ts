/** Error carrying the HTTP status and the backend's `detail` message. */
export class ApiError extends Error {
  status: number;
  constructor(status: number, detail: string) {
    super(detail);
    this.name = "ApiError";
    this.status = status;
  }
}

/** A failure in a shape the UI can act on: the message to show, and the status
 *  that decides what to offer next (409 means "fix your library"). */
export interface ErrorState {
  status: number;
  message: string;
}

/**
 * The one way a caught `unknown` becomes an ErrorState. Anything that is not
 * an ApiError has no status to act on — it gets 0, which no branch treats
 * specially.
 */
export function toErrorState(err: unknown, fallback = "That did not work. Try again."): ErrorState {
  if (err instanceof ApiError) return { status: err.status, message: err.message };
  return { status: 0, message: err instanceof Error ? err.message : fallback };
}
