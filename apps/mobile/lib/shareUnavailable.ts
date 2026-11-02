/** A file share this build cannot make, kept free of React Native so pure modules can read it. */

/** This build cannot hand a file to the share sheet (Android without expo-sharing): an app update fixes it. */
export class SharingUnavailableError extends Error {
  constructor() {
    super("Sharing files needs an app update.");
    this.name = "SharingUnavailableError";
  }
}

/**
 * The words for a failed file share: an update for a build that cannot share files, else the
 * caller's own line (null: its default). Each screen that shares a file reads it, so none
 * shows its generic line where an update is the fix.
 */
export function shareFailureKey<Fallback extends string | null>(error: unknown, fallbackKey: Fallback): string | Fallback {
  return error instanceof SharingUnavailableError ? "common.share_needs_update" : fallbackKey;
}
