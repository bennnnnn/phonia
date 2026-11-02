import { useCallback, useRef, useState } from "react";
import { useTranslation } from "react-i18next";

import { useAuth } from "@/contexts/AuthContext";
import { useActionFeedbackOptional } from "@/contexts/actionFeedbackCore";
import { useAccountDelete } from "@/hooks/useAccountDelete";
import { accountDeleteFailureKey } from "@/lib/accountDelete";
import { agreeToAiDataSharing } from "@/lib/api";
import { writeCachedUser } from "@/lib/cachedUser";
import { tap } from "@/lib/haptics";
import { reportRecoverableError } from "@/lib/reportRecoverableError";
import { confirmDialog } from "@/ui/overlay/dialogs";

type ConsentChoice = "agree" | "decline" | "delete";

/**
 * Agree (stored on the account, so every device knows), leave by signing out, or delete
 * the account: someone who does not agree never reaches Settings, where deleting lives.
 */
export function useAiConsentActions() {
  const { token, mergeUser, signOut } = useAuth();
  const { t } = useTranslation();
  const feedback = useActionFeedbackOptional();
  const deleteAndSignOut = useAccountDelete();
  const busyRef = useRef(false);
  const [busy, setBusy] = useState<ConsentChoice | null>(null);

  const run = useCallback(
    async (choice: ConsentChoice, action: () => Promise<void>) => {
      if (busyRef.current) return;
      tap();
      busyRef.current = true;
      setBusy(choice);
      try {
        await action();
      } catch {
        reportRecoverableError(feedback, t("onboarding.consent_failed"));
      } finally {
        busyRef.current = false;
        setBusy(null);
      }
    },
    [feedback, t],
  );

  const agree = useCallback(
    () =>
      run("agree", async () => {
        if (!token) return;
        const updated = await agreeToAiDataSharing(token);
        // The screen's own gate then sends the user on to the chat.
        mergeUser(updated);
        void writeCachedUser(updated);
      }),
    [mergeUser, run, token],
  );

  const decline = useCallback(() => run("decline", signOut), [run, signOut]);

  const deleteAccount = useCallback(async () => {
    if (busyRef.current) return;
    const ok = await confirmDialog({
      title: t("delete.title"),
      message: t("delete.message"),
      cancelLabel: t("common.cancel"),
      confirmLabel: t("common.delete"),
      destructive: true,
    });
    if (!ok) return;
    busyRef.current = true;
    setBusy("delete");
    // Signed out on success: the screen's gate then goes to sign-in.
    const outcome = await deleteAndSignOut();
    busyRef.current = false;
    setBusy(null);
    if (outcome === "failed" || outcome === "unavailable") {
      reportRecoverableError(feedback, t(accountDeleteFailureKey(outcome)));
    }
  }, [deleteAndSignOut, feedback, t]);

  return { busy, agree, decline, deleteAccount };
}
