/** Preset caption for the camera math solver entry point. The API recognizes this
 * exact string (apps/api/app/services/subject_scan.py); both sides compare it with
 * docs/fixtures/scanner_prompts.json.
 *
 * Kept in its own dependency-free module so consumers that only need the string —
 * like messageAttachments.ts, which Jest tests without Expo native-module mocks —
 * don't pull in expo-document-picker/expo-image-picker/expo-file-system transitively. */
export const MATH_CAMERA_PROMPT = "Solve the math problem in this image step by step.";

/** The steps ask a confirmed scan is sent with; the API lessons read it. */
const MATH_SCAN_SOLVE_PREFIX = "Show steps:";

const RELATION = /[=<>\u2264\u2265]/;

/**
 * The message a confirmed scan sends as ordinary text, so the whole text
 * pipeline (lessons, systems, word problems) sees it. Relations on separate
 * lines join with commas ("x+y=5, x-y=1") so a system reads as one problem,
 * also under the instruction printed above it; any other lines join with spaces.
 */
export function mathScanSolveMessage(reading: string): string {
  const lines = reading
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean);
  if (lines.length === 0) return "";
  const joined = lines.reduce((text, line, i) => {
    const between = RELATION.test(line) && RELATION.test(lines[i - 1]) ? ", " : " ";
    return `${text}${between}${line}`;
  });
  return `${MATH_SCAN_SOLVE_PREFIX} ${joined}`;
}
