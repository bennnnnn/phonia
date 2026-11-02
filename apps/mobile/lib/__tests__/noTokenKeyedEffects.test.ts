/**
 * Structural guard: an effect never re-runs because the bearer token rotated.
 *
 * The access token refreshes hourly. Effects keyed on it re-read the model list and the
 * usage, took a GPS fix, restarted downloads and made a new draft chat every hour
 * (code-health audit NET-11). Key an effect on `useAccountSession().account` (or a
 * signed-in boolean) and read `getToken()` when the request goes out.
 */

import { appFiles, isTest, readSource, relative } from "@/lib/__tests__/support/sourceFiles";

/** `file` → why its token-keyed effect does no I/O. */
const ALLOWED: Record<string, string> = {
  "features/attachments/components/ChatMessageImage.tsx": "clears a failed image so it retries with the new token",
};

const CLOSES_DEPS = /^(\s*)\}, \[([^\]]*)\]\);/;
const HOOK = /\buse(Effect|LayoutEffect|Callback|Memo)\(/;

/** Each effect (not callback or memo) whose dependency list names `token`. */
function tokenKeyedEffects(text: string): number[] {
  const lines = text.split("\n");
  const found: number[] = [];
  lines.forEach((line, index) => {
    const deps = CLOSES_DEPS.exec(line);
    if (!deps || !/\btoken\b/.test(deps[2] ?? "")) return;
    const indent = deps[1] ?? "";
    for (let above = index - 1; above >= 0; above -= 1) {
      const opener = lines[above] ?? "";
      const hook = HOOK.exec(opener);
      if (hook && opener.startsWith(indent) && !opener.startsWith(`${indent} `)) {
        if (hook[1] === "Effect" || hook[1] === "LayoutEffect") found.push(index + 1);
        return;
      }
    }
  });
  return found;
}

describe("token-keyed effects", () => {
  it("sees an effect keyed on the token, and not a callback", () => {
    expect(tokenKeyedEffects("  useEffect(() => {\n    load(token);\n  }, [token]);")).toEqual([3]);
    expect(tokenKeyedEffects("  const send = useCallback(() => {\n    go(token);\n  }, [token]);")).toEqual([]);
  });

  it("no effect re-runs when the token rotates", () => {
    const found = appFiles()
      .filter((file) => !isTest(file) && !(relative(file) in ALLOWED))
      .flatMap((file) => tokenKeyedEffects(readSource(file)).map((line) => `${relative(file)}:${line}`));
    expect(found).toEqual([]);
  });

  it("every allowance still applies", () => {
    const stale = Object.keys(ALLOWED).filter((file) => {
      const path = appFiles().find((candidate) => relative(candidate) === file);
      return !path || tokenKeyedEffects(readSource(path)).length === 0;
    });
    expect(stale).toEqual([]);
  });
});
