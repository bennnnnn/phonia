import { mathScanSolveMessage } from "@/lib/math/cameraPrompt";
import { scannerCameraPrompt, type ScannerSubject } from "@/lib/scanner/subjects";

/** Subjects whose scan is read back for the student to confirm before solving. */
const READ_BACK_SUBJECTS = ["math", "physics", "chemistry"] as const;

export type ReadBackSubject = (typeof READ_BACK_SUBJECTS)[number];

export function readsBack(subject: ScannerSubject): subject is ReadBackSubject {
  return (READ_BACK_SUBJECTS as readonly ScannerSubject[]).includes(subject);
}

/** Protocol line a photo carries after the student confirms the reading. Must
 * stay byte-for-byte identical to SCAN_CONFIRMED_PREFIX on the API. */
export const SCAN_CONFIRMED_PREFIX = "I read this as:";

/**
 * Caption for a photo sent from the review: the subject's camera line, then
 * the reading the student checked, so the API solves that instead of reading
 * the photo again. With no reading, the camera line alone.
 *
 * The API ends the reading at the first blank line, where a typed draft or an
 * attachment note follows. The reading keeps its lines, but never a blank one,
 * so a reading edited into paragraphs still arrives whole.
 */
export function composerTextAfterScanConfirm(reading: string, subject: ScannerSubject): string {
  const prompt = scannerCameraPrompt(subject);
  const lines = reading
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean);
  return lines.length ? `${prompt}\n\n${SCAN_CONFIRMED_PREFIX} ${lines.join("\n")}` : prompt;
}

/**
 * The message a confirmed reading is sent as. Math asks for steps; physics
 * and chemistry send the problem as the student would type it, so it is
 * verified and answered like a typed question.
 */
export function scanSolveMessage(reading: string, subject: ScannerSubject): string {
  return subject === "math" ? mathScanSolveMessage(reading) : reading.trim();
}
