import { getSessionGeneration, requireTokenSession, SessionChangedError } from "@/lib/auth";

/** Fence file reads and native share/save actions as well as authenticated HTTP. */
export function attachmentSessionGuard(token?: string | null): () => void {
  if (token) requireTokenSession(token);
  const generation = getSessionGeneration();
  return () => {
    if (generation !== getSessionGeneration()) throw new SessionChangedError();
    if (token) requireTokenSession(token);
  };
}
