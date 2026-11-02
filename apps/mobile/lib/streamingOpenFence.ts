/**
 * Classify the unstable streaming tail when a fence / block-math delimiter
 * is still open. Callers render these as plain text so markdown-it (+ Prism)
 * does not re-tokenize a growing open fence every throttle tick.
 */

import { readFenceMarker, type OpenFence } from "@/lib/mdFenceScan";

type OpenStreamScan = {
  openFence: OpenFence | null;
  dollarOpen: boolean;
  bracketDepth: number;
};

type OpenStreamRegion =
  | { kind: "fence"; lang: string; body: string }
  | { kind: "math"; body: string }
  | { kind: "other"; text: string };

/** Closing ``` / ~~~ arrives in the open-fence body before the scan sees the
 * fence close — AnswerBlock then shows leftover backticks (and `` looking like
 * "..") until the fence is classified closed. */
export function stripTrailingFenceCloser(body: string): string {
  return body.replace(/(?:\r?\n)?[`~]{1,3}\s*$/, "");
}

/** The tail's opener line read with the one fence grammar, and the body after it. */
export function parseOpenFenceTail(liveRaw: string): { lang: string; body: string } | null {
  const newline = liveRaw.indexOf("\n");
  const marker = readFenceMarker(newline < 0 ? liveRaw : liveRaw.slice(0, newline));
  if (!marker) return null;
  return {
    lang: marker.info,
    body: stripTrailingFenceCloser(newline < 0 ? "" : liveRaw.slice(newline + 1)),
  };
}

export function parseOpenMathTail(liveRaw: string): string | null {
  if (liveRaw.startsWith("$$")) {
    const rest = liveRaw.slice(2);
    return rest.startsWith("\n") ? rest.slice(1) : rest;
  }
  if (liveRaw.startsWith("\\[")) {
    const rest = liveRaw.slice(2);
    return rest.startsWith("\n") ? rest.slice(1) : rest;
  }
  return null;
}

export function classifyOpenStreamTail(
  liveRaw: string,
  scan: OpenStreamScan | null | undefined,
): OpenStreamRegion {
  if (!liveRaw) return { kind: "other", text: "" };

  if (scan?.openFence) {
    const fence = parseOpenFenceTail(liveRaw);
    if (fence) return { kind: "fence", lang: fence.lang, body: fence.body };
  }

  if (scan?.dollarOpen || (scan?.bracketDepth ?? 0) !== 0) {
    const body = parseOpenMathTail(liveRaw);
    if (body != null) return { kind: "math", body };
  }

  return { kind: "other", text: liveRaw };
}
