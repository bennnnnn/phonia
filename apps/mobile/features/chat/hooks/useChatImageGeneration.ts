import { useCallback } from "react";

import { useImageGeneration } from "@/features/images/hooks/useImageGeneration";
import { uploadSendAttachment } from "@/features/chat/hooks/useSendAttachment";
import { refusalCode, resolveChatError } from "@/features/chat/model/errorMessage";
import { AttachmentError, attachmentErrorMessage } from "@/features/attachments/model/attachmentErrors";
import { ApiRequestError } from "@/lib/api/errorBody";
import { isServerUnreachable } from "@/lib/api/deadline";

type Options = Omit<Parameters<typeof useImageGeneration>[0], "uploadReference" | "describeFailure"> & {
  isPaid: boolean;
};

/** A picture that failed before the API answered, in the phone's words. */
function localFailure(error: unknown, t: (key: string) => string): string {
  if (isServerUnreachable(error)) return t("chat.error_unreachable");
  return error instanceof AttachmentError ? attachmentErrorMessage(error, t) : t("chat.error_generic");
}

/** Image generation on the chat screen: the chat uploads its reference photo and words its failures. */
export function useChatImageGeneration({ isPaid, t, ...options }: Options) {
  const describeFailure = useCallback(
    (message: string, code: string | undefined, error: unknown) => {
      // The image service failed (its 502): the picture's own line, where its English showed.
      if (code === "upstream_failed") return { message: t("chat.image_gen_failed"), retryable: true };
      // Not the API's answer: no connection, or the reference photo's upload. Its English
      // showed on the card ("Could not reach the Recall server…", "ATTACHMENT_TOO_LARGE").
      if (!(error instanceof ApiRequestError)) return { message: localFailure(error, t), retryable: true };
      // Every daily_limit from the picture endpoint is the picture's own cap.
      const resolved = resolveChatError({ message, code: refusalCode(code, "image_generation"), isPaid, t });
      // A spent allowance or a refused picture (the chat's quota and notice kinds) fails again.
      return { message: resolved.message, retryable: resolved.kind !== "quota" && resolved.kind !== "notice" };
    },
    [isPaid, t],
  );
  return useImageGeneration({ ...options, t, uploadReference: uploadSendAttachment, describeFailure });
}
