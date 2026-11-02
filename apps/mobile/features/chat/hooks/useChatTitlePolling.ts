import { useCallback, useEffect, useRef, useState } from "react";

import { api } from "@/lib/api";
import { getSessionGeneration } from "@/lib/auth";
import { useLatestRef } from "@/lib/latestRef";
import { useViewOwner } from "@/features/chat/hooks/useViewOwner";
import { getCachedChat, peekCreatedChat } from "@/features/chat/model/chatListCache";
import { firstReplyTitlePlan } from "@/features/chat/model/titleRefresh";
import {
  getChatMutationRevision,
  insertChatGlobal,
  isChatTitleGenerating,
  patchChatGlobal,
  setChatTitleGenerating,
} from "@/features/chat/drawer/drawer";

type Options = {
  token: string | null;
  chatId: string | null;
  setChatTitle: (title: string | null) => void;
  getFirstUserText?: () => string | undefined;
};
type TitlePoll = { cancel: () => void; task: Promise<void> };
const TITLE_POLL_ATTEMPTS = 8;
const TITLE_POLL_MS = 2000;

/** Polls for the auto-generated chat title after the first assistant reply. */
export function useChatTitlePolling({ token, chatId, setChatTitle, getFirstUserText }: Options) {
  const [titleGenerating, setTitleGenerating] = useState(false);
  const session = getSessionGeneration();
  // The header shows one chat's title; a poll from another view leaves it alone.
  const { currentView } = useViewOwner(`${chatId}:${session}`);
  const headerChatId = useLatestRef(chatId);
  const mounted = useRef(true);
  const polls = useRef(new Map<string, TitlePoll>());
  useEffect(() => {
    mounted.current = true;
    const active = polls.current;
    return () => {
      mounted.current = false;
      for (const poll of active.values()) poll.cancel();
      active.clear();
    };
  }, [session]);

  const pollForTitle = useCallback((tid: string, cid: string): Promise<void> => {
    if (!mounted.current || session !== getSessionGeneration()) return Promise.resolve();
    const existing = polls.current.get(cid);
    if (existing) return existing.task;
    const ownerSession = session;
    const owner = currentView();
    let revision = getChatMutationRevision(cid);
    let cancelled = false;
    let wake: (() => void) | undefined;
    const isCurrent = () => mounted.current && !cancelled && ownerSession === getSessionGeneration();
    const ownsHeader = () => isCurrent() && owner === currentView() && cid === headerChatId.current;
    const poll: TitlePoll = {
      cancel: () => { cancelled = true; wake?.(); },
      task: Promise.resolve(),
    };
    polls.current.set(cid, poll);
    setChatTitleGenerating(cid);
    if (ownsHeader()) setTitleGenerating(true);
    poll.task = (async () => {
      try {
        for (let i = 0; i < TITLE_POLL_ATTEMPTS; i++) {
          await new Promise<void>((resolve) => {
            const timer = setTimeout(resolve, TITLE_POLL_MS);
            wake = () => { clearTimeout(timer); resolve(); };
          });
          wake = undefined;
          if (!isCurrent()) return;
          const latestRevision = getChatMutationRevision(cid);
          if (revision !== latestRevision) {
            const latest = getCachedChat(cid);
            // An optimistic rename already owns the displayed title. A removed
            // row must not be revived by a poll that started before deletion.
            if (!latest || latest.title?.trim()) return;
            revision = latestRevision;
          }
          try {
            const updated = await api.getChat(tid, cid);
            if (!isCurrent() || revision !== getChatMutationRevision(cid)) return;
            // API titles are persisted values; short manual labels are valid too.
            if (updated.title?.trim()) {
              patchChatGlobal(cid, { title: updated.title });
              if (ownsHeader()) setChatTitle(updated.title);
              return;
            }
          } catch {
            /* Topic generation and drawer refresh are best-effort. */
          }
        }
      } finally {
        if (ownsHeader()) setTitleGenerating(false);
        if (ownerSession === getSessionGeneration() && isChatTitleGenerating(cid)) {
          setChatTitleGenerating(null);
        }
        if (polls.current.get(cid) === poll) polls.current.delete(cid);
      }
    })();
    return poll.task;
  }, [session, setChatTitle, currentView, headerChatId]);

  const handleFirstReply = useCallback(async (explicitChatId?: string | null) => {
    const cid = explicitChatId ?? chatId;
    if (!token || !cid || !mounted.current || session !== getSessionGeneration()) return;
    const ownerSession = session;
    const owner = currentView();
    const revision = getChatMutationRevision(cid);
    const isCurrent = () => mounted.current && ownerSession === getSessionGeneration() &&
      revision === getChatMutationRevision(cid);
    const ownsHeader = () => mounted.current && ownerSession === getSessionGeneration() &&
      owner === currentView() && cid === headerChatId.current;
    const plan = firstReplyTitlePlan(peekCreatedChat(cid), getCachedChat(cid), getFirstUserText?.());
    let shouldPoll = plan.poll;
    if (plan.insert) {
      insertChatGlobal(plan.insert);
      if (plan.insert.title && ownsHeader()) setChatTitle(plan.insert.title);
    } else if (plan.fetch) {
      try {
        const chat = await api.getChat(token, cid);
        if (!isCurrent()) return;
        insertChatGlobal(chat);
        if (chat.title?.trim()) {
          if (ownsHeader()) setChatTitle(chat.title);
          shouldPoll = false;
        }
      } catch {
        if (!isCurrent()) return;
        /* Drawer insert is best-effort. */
      }
    }
    if (shouldPoll) await pollForTitle(token, cid);
  }, [token, session, chatId, pollForTitle, setChatTitle, getFirstUserText, currentView, headerChatId]);

  useEffect(() => {
    setTitleGenerating(false);
    if (!chatId) setChatTitleGenerating(null);
  }, [chatId, session]);

  return { titleGenerating, pollForTitle, handleFirstReply };
}
