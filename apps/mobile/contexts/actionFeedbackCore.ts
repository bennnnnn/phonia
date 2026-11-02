import { createContext, useContext } from "react";

import type { IconName } from "@/ui/icons/names";

export type ActionFeedbackTone = "success" | "info" | "warning" | "error";

export type ActionFeedbackOptions = {
  tone?: ActionFeedbackTone;
  icon?: IconName;
  haptic?: boolean;
};

export type ActionFeedbackApi = {
  show: (message: string, options?: ActionFeedbackOptions) => void;
  success: (
    message: string,
    options?: Omit<ActionFeedbackOptions, "tone">,
  ) => void;
  info: (message: string, options?: Omit<ActionFeedbackOptions, "tone">) => void;
  warning: (
    message: string,
    options?: Omit<ActionFeedbackOptions, "tone">,
  ) => void;
  error: (message: string, options?: Omit<ActionFeedbackOptions, "tone">) => void;
  dismiss: () => void;
  /**
   * Lets a provider mounted over this one (inside a full-screen modal) show
   * this one's toasts while it is mounted; a toast under the modal could not
   * be seen. Returns the release. Providers set it; test doubles may omit it.
   */
  capture?: (overlay: ActionFeedbackApi) => () => void;
};

export const ActionFeedbackContext = createContext<ActionFeedbackApi | null>(null);

export function useActionFeedback(): ActionFeedbackApi {
  const value = useContext(ActionFeedbackContext);
  if (!value) {
    throw new Error("useActionFeedback must be used within ActionFeedbackProvider");
  }
  return value;
}

/** Useful for isolated hooks/tests that can also run outside the app root. */
export function useActionFeedbackOptional(): ActionFeedbackApi | null {
  return useContext(ActionFeedbackContext);
}
