/**
 * A cleared composer that iOS autocorrect fills again.
 *
 * Send clears the field, then dismisses the keyboard. Dismissing commits the keyboard's
 * pending correction of the text it still remembers, and that arrives as a typed change
 * after the clear: "im in indianapolis" came back as "I'm in Indianapolis", or as the
 * half "I'm in ", and was sent again with the next message. Such a change is dropped for
 * a moment after the clear. The keyboard is going down then, so the user isn't typing.
 */

export const SEND_ECHO_MS = 800;

export type ClearedText = { text: string; at: number };

function words(text: string): string[] {
  const normalized = text.toLocaleLowerCase().replace(/[‘’]/g, "'").trim();
  return normalized ? normalized.split(/\s+/) : [];
}

/** True when ``text`` is the keyboard giving back ``cleared``, not the user typing. */
export function isSendEcho(cleared: ClearedText | null, text: string, now: number): boolean {
  if (!cleared || now - cleared.at > SEND_ECHO_MS) return false;
  const was = words(cleared.text);
  const echo = words(text);
  if (echo.length === 0 || echo.length > was.length) return false;
  const same = echo.filter((word, index) => word === was[index]).length;
  // The half it remembered ("I'm in "), or the whole with a word or two corrected.
  const prefix = was.join(" ").startsWith(echo.join(" "));
  return prefix || (echo.length === was.length && same >= Math.ceil(was.length * 0.6));
}
