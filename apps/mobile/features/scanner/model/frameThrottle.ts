/**
 * How often the live scanner reads a camera frame. Read back to back, ML Kit ran text
 * recognition up to 30 times a second for as long as the scanner stayed open, warming
 * the phone, though three equal reads settle the text: at this rate, in under half a
 * second.
 */
export const LIVE_READ_INTERVAL_MS = 150;

/** Whether a frame arriving at ``now`` (ms) is read; the last read was at ``lastReadAt``. */
export function shouldReadFrame(lastReadAt: number, now: number, intervalMs: number): boolean {
  "worklet";
  return now - lastReadAt >= intervalMs || now < lastReadAt;
}
