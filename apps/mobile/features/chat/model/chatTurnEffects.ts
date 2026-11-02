import type { Dispatch, SetStateAction } from "react";
import { AccessibilityInfo } from "react-native";

import type { Message } from "@/lib/api";
import { notifyConsentRequired } from "@/lib/api/consentRefusal";
import { clearPendingChatTtft, markChatFirstToken } from "@/features/chat/model/latency";
import { withdrawFromOpenedPage } from "@/features/chat/model/openedPage";
import type { createStreamCueGate } from "@/features/chat/model/streamFeedback";
import type { TurnUsage } from "@/features/chat/model/socketReduce";
import {
  beginTurnOutcome,
  noteTurnActivity,
  noteTurnSendReady,
  noteTurnToken,
  reportTurnOutcome,
} from "@/features/chat/model/turnOutcome";
import type { ChatTurnCommand, DroppedTurnFollow } from "@/features/chat/model/chatTurnCore";

/** What the chat turn's commands act on: the screen's state, the transport and the callers. */
export type ChatTurnEffects = {
  t: (key: string) => string;
  setMessages: Dispatch<SetStateAction<Message[]>>;
  /** Pops the last answer for Regenerate from the newest list. */
  popForRegenerate: () => void;
  cue: ReturnType<typeof createStreamCueGate>;
  onError?: (message: string, code?: string) => void;
  onFirstReply?: () => void;
  onTodosSync?: () => void;
  onUsage?: (usage: TurnUsage) => void;
  dropSocket: () => void;
  abortSse: () => void;
  cancelSocket: (streamedChars?: number) => void;
  followDroppedTurn: (follow: DroppedTurnFollow, polls?: number, pollMs?: (poll: number) => number) => void;
};

function runCommand(command: ChatTurnCommand, effects: ChatTurnEffects): void {
  switch (command.type) {
    case "messages":
      effects.setMessages(command.update);
      return;
    case "pop_for_regenerate":
      effects.popForRegenerate();
      return;
    case "cue":
      effects.cue[command.cue]();
      return;
    case "outcome":
      if (command.outcome === "begin") beginTurnOutcome();
      else if (command.outcome === "token") noteTurnToken();
      else if (command.outcome === "send_ready") noteTurnSendReady();
      else if (command.outcome === "activity") noteTurnActivity(command.phase);
      else reportTurnOutcome(command.completion, command.code);
      return;
    case "first_token":
      markChatFirstToken(command.turnId, command.frame);
      return;
    case "clear_ttft":
      clearPendingChatTtft(command.turnId);
      return;
    case "announce":
      AccessibilityInfo.announceForAccessibility(effects.t(command.key));
      return;
    case "consent_required":
      notifyConsentRequired();
      return;
    case "report_error":
      effects.onError?.(command.message ?? effects.t(command.key), command.code);
      return;
    case "first_reply":
      effects.onFirstReply?.();
      return;
    case "todos_changed":
      effects.onTodosSync?.();
      return;
    case "usage":
      effects.onUsage?.(command.usage);
      return;
    case "drop_socket":
      effects.dropSocket();
      return;
    case "abort_sse":
      effects.abortSse();
      return;
    case "cancel_socket":
      effects.cancelSocket(command.streamedChars);
      return;
    case "retry_fallback":
      void command.fallback.retry();
      return;
    case "follow_dropped_turn":
      effects.followDroppedTurn(command.follow, command.polls, command.pollMs);
      return;
    case "withdraw_unsent":
      withdrawFromOpenedPage(command.chatId, command.pending);
      // The flag lives on the send its sender holds: it then returns the draft.
      if (command.pending && !command.pending.dispatched) command.pending.takenBack ??= "stop";
      return;
  }
}

/** Runs what one chat turn step asks for, in the order it asks. */
export function runChatTurnCommands(commands: readonly ChatTurnCommand[], effects: ChatTurnEffects): void {
  for (const command of commands) runCommand(command, effects);
}
