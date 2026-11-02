import React, { createContext, useContext } from "react";

import type { EmailDraft } from "@/lib/richBlocks";

type SaveEmailDraft = (messageId: string, draft: EmailDraft) => Promise<boolean>;

const EmailDraftSaveContext = createContext<SaveEmailDraft | null>(null);
const AssistantMessageIdContext = createContext<string | null>(null);

export function EmailDraftPersistProvider({
  save,
  children,
}: {
  save: SaveEmailDraft;
  children: React.ReactNode;
}) {
  return (
    <EmailDraftSaveContext.Provider value={save}>{children}</EmailDraftSaveContext.Provider>
  );
}

export function AssistantMessageScope({
  messageId,
  children,
}: {
  messageId: string;
  children: React.ReactNode;
}) {
  return (
    <AssistantMessageIdContext.Provider value={messageId}>
      {children}
    </AssistantMessageIdContext.Provider>
  );
}

export function useEmailDraftSave(): SaveEmailDraft | null {
  return useContext(EmailDraftSaveContext);
}

export function useAssistantMessageId(): string | null {
  return useContext(AssistantMessageIdContext);
}
