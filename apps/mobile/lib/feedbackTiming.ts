import type { ActionFeedbackTone } from "@/contexts/actionFeedbackCore";

/** How long a transient banner stays. Errors that need a next step use ChatInlineError. */
export const ACTION_BANNER_MS: Record<ActionFeedbackTone, number> = {
  success: 2000,
  info: 3000,
  warning: 4000,
  error: 5000,
};
