import { notifyError, selection, tap } from "@/lib/haptics";

type StreamCue = "activity" | "complete" | "stopped" | "error";

/** One cue per turn. Never per token. A finished reply is a light tap. */
export function playStreamCue(cue: StreamCue): void {
  if (cue === "activity") selection();
  else if (cue === "complete" || cue === "stopped") tap();
  else notifyError();
}

export function createStreamCueGate() {
  let heardActivity = false;
  let settled = false;
  return {
    reset() {
      heardActivity = false;
      settled = false;
    },
    activity() {
      if (heardActivity || settled) return;
      heardActivity = true;
      playStreamCue("activity");
    },
    complete() {
      if (settled) return;
      settled = true;
      playStreamCue("complete");
    },
    stopped() {
      if (settled) return;
      settled = true;
      playStreamCue("stopped");
    },
    error() {
      if (settled) return;
      settled = true;
      playStreamCue("error");
    },
  };
}
