import { useCallback, useState } from "react";
import { useTranslation } from "react-i18next";

import { useAuth } from "@/contexts/AuthContext";
import { useActionFeedbackOptional } from "@/contexts/actionFeedbackCore";
import { invalidateMemoryDocuments } from "@/features/memory/model/memoryDocumentsCache";
import { setMemoriesCache } from "@/features/memory/model/memoryListCache";
import { api } from "@/lib/api";
import { notifyDestructive } from "@/lib/haptics";
import { reportRecoverableError } from "@/lib/reportRecoverableError";
import { confirmDialog } from "@/ui/overlay/dialogs";

/**
 * "Clear all memories", from any memory page's menu: confirm, delete every
 * saved fact, and empty the memory caches. Resolves true once they are gone.
 */
export function useClearAllMemories(isCurrentView: () => boolean) {
  const { token } = useAuth();
  const { t } = useTranslation();
  const feedback = useActionFeedbackOptional();
  const [busy, setBusy] = useState(false);

  const clearAll = useCallback(async (): Promise<boolean> => {
    if (!token || !isCurrentView() || busy) return false;
    const ok = await confirmDialog({
      title: t("settings.memory_clear_all_confirm_title"),
      message: t("settings.memory_clear_all_confirm_body"),
      cancelLabel: t("common.cancel"),
      confirmLabel: t("common.delete"),
      destructive: true,
    });
    if (!ok || !isCurrentView()) return false;
    setBusy(true);
    try {
      await api.clearMemories(token);
      setMemoriesCache([]);
      invalidateMemoryDocuments();
      notifyDestructive();
      return true;
    } catch {
      if (isCurrentView()) reportRecoverableError(feedback, t("common.error"));
      return false;
    } finally {
      if (isCurrentView()) setBusy(false);
    }
  }, [token, isCurrentView, busy, t, feedback]);

  return { clearAll, busy };
}
