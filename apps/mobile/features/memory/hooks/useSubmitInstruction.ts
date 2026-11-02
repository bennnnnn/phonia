import { useCallback } from "react";
import { useTranslation } from "react-i18next";

import { useActionFeedbackOptional } from "@/contexts/actionFeedbackCore";
import type { useMemoryDocuments } from "@/features/memory/hooks/useMemoryDocuments";
import { instructNotice } from "@/features/memory/model/instructNotice";
import { memoryFailureKey } from "@/features/memory/model/memoryFailure";
import { reportRecoverableError } from "@/lib/reportRecoverableError";

type Instruct = ReturnType<typeof useMemoryDocuments>["instruct"];

/**
 * The memory box's send, from the Memory list or one page (`topic`): send the
 * instruction and say how it landed. Resolves true when the box should clear.
 */
export function useSubmitInstruction(
  instruct: Instruct,
  isCurrentView: () => boolean,
  topic?: string,
) {
  const { t } = useTranslation();
  const feedback = useActionFeedbackOptional();

  return useCallback(async (instruction: string): Promise<boolean> => {
    const outcome = await instruct(instruction, topic);
    if (!isCurrentView()) return false;
    if (!outcome.ok) {
      reportRecoverableError(feedback, t(memoryFailureKey(outcome.failure, "memory.instruct_failed")));
      return false;
    }
    const notice = instructNotice(outcome, t);
    if (notice.landed) feedback?.success(notice.message);
    else feedback?.warning(notice.message);
    return notice.landed;
  }, [instruct, topic, isCurrentView, feedback, t]);
}
