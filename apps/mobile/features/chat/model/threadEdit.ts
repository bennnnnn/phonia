import type { SetStateAction } from "react";

import type { Message } from "@/lib/api";

/**
 * Every writer of the thread on screen besides the turn's own frames. Each change goes
 * through the turn reducer (`thread_edit`, chatTurnState.ts), so one owner sequences every
 * edit of the list; `useChat` is the only caller of the React setter.
 */
export type ThreadEditSource =
  /** A photo or file deleted in Library leaves the bubbles that showed it. */
  | "attachment_deleted"
  /** New chat, or a route that opens no chat: the list empties. */
  | "view_cleared"
  /** An opened chat paints its cached copy before the server's page arrives. */
  | "cached_paint"
  /** The opened chat's page from the server, merged with what was painted. */
  | "opened_page"
  /** A refetch of the open chat (foreground, focus, a todo change). */
  | "page_refresh"
  | "older_page"
  | "newer_page"
  /** The window around one message (a search hit). */
  | "window_around"
  /** Back from a window to the newest page. */
  | "latest_page"
  | "feedback"
  | "email_draft_saved"
  /** The bubble the composer paints the moment a send starts. */
  | "optimistic_send"
  /** A send that failed before reaching the server takes its bubble back. */
  | "failed_send_withdrawn"
  /** A picture turn: its bubbles, its result or its failure. */
  | "image_turn"
  /** Live talk's spoken turns, written into the chat as they happen. */
  | "live_talk";

/** The new list, or how to make it from the newest one. */
export type ThreadUpdate = SetStateAction<Message[]>;

/**
 * Changes the thread on screen; `source` says which writer it is. `chatId`, when given, is
 * the chat the change belongs to: work that outlives its chat (a picture still generating
 * when the user opens another chat) waits for that chat instead of landing in the one on
 * screen. The chat's writer answers false for a change that waits; a writer with nothing
 * to tell (a test's list) answers nothing.
 */
export type EditThread = (update: ThreadUpdate, source: ThreadEditSource, chatId?: string) => boolean | void;
