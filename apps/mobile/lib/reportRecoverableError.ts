import type { ActionFeedbackApi } from "@/contexts/actionFeedbackCore";
import { alertDialog } from "@/ui/overlay/dialogs";

/** Recoverable failures: in-tree banner when the provider exists, native fallback otherwise. */
export function reportRecoverableError(
  feedback: ActionFeedbackApi | null | undefined,
  message: string,
): void {
  if (feedback) {
    feedback.error(message);
    return;
  }
  void alertDialog({ title: message });
}

export function reportRecoverableWarning(
  feedback: ActionFeedbackApi | null | undefined,
  message: string,
): void {
  if (feedback) {
    feedback.warning(message);
    return;
  }
  void alertDialog({ title: message });
}
