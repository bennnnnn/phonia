/** True when the person closed the OS share or print sheet without sharing. */
export function isShareCancelled(error: unknown): boolean {
  if (!error || typeof error !== "object") return false;
  const message = "message" in error ? String((error as { message?: unknown }).message) : "";
  // iOS often throws "User did not share"; Android uses cancel/dismiss.
  return /cancel|dismiss|did not share/i.test(message);
}
