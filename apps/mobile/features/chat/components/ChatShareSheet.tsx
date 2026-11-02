import { useEffect, useRef } from "react";
import { useTranslation } from "react-i18next";

import type { Message } from "@/lib/api";
import { NothingToExportError } from "@/features/chat/model/nothingToExport";
import { conversationTranscript } from "@/features/chat/model/transcript";
import { formatDate } from "@/lib/datetime/format";
import { shareFailureKey } from "@/lib/shareUnavailable";
import { ShareSheet } from "@/ui/share/ShareSheet";
import { useLatestRef } from "@/lib/latestRef";

const APP_ICON = require("@/assets/images/icon.png");

type Props = {
  visible: boolean;
  onClose: () => void;
  title: string | null;
  /** Every message in the chat. Loaded once each time the sheet opens. */
  loadMessages: () => Promise<Message[]>;
};

/** Share a chat as it is now: the OS share menu, Copy, or a PDF. */
export function ChatShareSheet({ visible, onClose, title, loadMessages }: Props) {
  const { t } = useTranslation();
  const messages = useRef<Promise<Message[]> | null>(null);
  const loadRef = useLatestRef(loadMessages);

  useEffect(() => {
    if (!visible) messages.current = null;
  }, [visible]);

  const getMessages = () => {
    if (!messages.current) {
      const pending = loadRef.current();
      messages.current = pending;
      pending.catch(() => {
        if (messages.current === pending) messages.current = null;
      });
    }
    return messages.current;
  };

  const shownTitle = title?.trim() || t("share.default_title");

  return (
    <ShareSheet
      visible={visible}
      onClose={onClose}
      heading={t("share.chat_heading")}
      note={t("share.chat_note")}
      preview={{
        title: shownTitle,
        meta: `${t("app.name")} · ${formatDate(new Date(), "monthDayYear")}`,
        image: APP_ICON,
      }}
      load={async () => conversationTranscript(title, await getMessages())}
      shareTitle={shownTitle}
      onExportPdf={async () => {
        // expo-print loads only when a PDF is asked for.
        const { exportConversationAsPdf } = await import("@/features/chat/model/exportMessagePdf");
        await exportConversationAsPdf(title, await getMessages());
      }}
      failureText={(error) => {
        if (error instanceof NothingToExportError) return t("chat.export_pdf_empty");
        const key = shareFailureKey(error, null);
        return key ? t(key) : null;
      }}
      labels={{
        share: t("share.action_share"),
        copy: t("share.action_copy"),
        copied: t("share.copied"),
        pdf: t("share.action_pdf"),
        copyText: t("share.copy_text"),
        failed: {
          share: t("chat.share_failed"),
          copy: t("share.copy_failed"),
          pdf: t("share.pdf_failed"),
        },
      }}
      testID="chat-share-sheet"
    />
  );
}
