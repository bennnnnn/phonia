import type { Message } from "@/lib/api";
import { ApiRequestError } from "@/lib/api/errorBody";
import { resolveChatError } from "@/features/chat/model/errorMessage";
import { initialChatTurnState, headRejectedSend, type ChatTurnCommand, type ChatTurnEvent, type ChatTurnState } from "@/features/chat/model/chatTurnCore";
import { reduceChatTurn } from "@/features/chat/model/chatTurnState";
import { popLastAssistantMessage } from "@/features/chat/model/regenerateLogic";
import type { PendingSend } from "@/features/chat/model/sendLogic";
import type { ChatSsePayload } from "@/features/chat/model/sse";
import { DUPLICATE_TURN_POLLS, duplicateTurnPollMs } from "@/features/chat/model/turnReconcile";
import type { ChatWsTransport } from "@/features/chat/model/wsTransport";

/**
 * The chat turn over recorded event sequences (code-health audit CLAR-04): each test
 * plays frames and actions through the pure reducer and reads the state, the
 * commands and the message list those commands leave.
 */
const NOW = Date.parse("2026-03-01T12:00:00Z");

function play(state: ChatTurnState, events: ChatTurnEvent[], start: Message[] = []) {
  let current = state;
  let list = start;
  const commands: ChatTurnCommand[] = [];
  for (const event of events) {
    const step = reduceChatTurn(current, event, NOW);
    current = step.state;
    for (const command of step.commands) {
      if (command.type === "messages") list = command.update(list);
      if (command.type === "pop_for_regenerate") list = popLastAssistantMessage(list).messages;
      commands.push(command);
    }
  }
  return { state: current, messages: list, commands, of: <T extends ChatTurnCommand["type"]>(type: T) =>
    commands.filter((command): command is Extract<ChatTurnCommand, { type: T }> => command.type === type) };
}

const frame = (payload: ChatSsePayload, ttftTurnId?: string | null): ChatTurnEvent => ({ type: "frame", payload, ttftTurnId });
const idle = (over: Partial<ChatTurnState> = {}): ChatTurnState => ({ ...initialChatTurnState("chat-1", 0), ...over });
const streaming = (over: Partial<ChatTurnState> = {}) => idle({ phase: "streaming", ...over });
const pending = (over: Partial<PendingSend> = {}): PendingSend => ({
  content: "hello", options: {}, messageId: "local-1", retryingRejected: false, dispatched: true, ...over,
});
const bubble: Message = { id: "streaming", role: "assistant", content: "", model: null, created_at: "t" };
const answer = (id: string, content: string): Message => ({ id, role: "assistant", content, model: null, created_at: "t" });
const cues = (commands: ChatTurnCommand[]) => commands.flatMap((command) => (command.type === "cue" ? [command.cue] : []));
const socket = {} as ChatWsTransport;

describe("frames", () => {
  it("start opens the stream and keeps the local status; after Stop it is ignored", () => {
    const stopped = play(idle({ draft: { content: "", status: "searching" } }), [frame({ type: "start" })]);
    expect(stopped.commands).toEqual([]);

    const run = play(streaming({ buffer: "stale", draft: { content: "", status: "searching", statusDetail: "cats" }, sendingMessageId: "local-1" }),
      [frame({ type: "start" })]);
    expect(cues(run.commands)).toEqual(["activity"]);
    expect(run.state).toMatchObject({ phase: "streaming", buffer: "", sendingMessageId: null, authFallback: null });
    expect(run.state.draft).toEqual({ content: "", status: "searching", statusDetail: "cats" });
    expect(run.messages).toEqual([expect.objectContaining({ id: "streaming" })]);
  });

  it("start marks the send taken by the server and keeps it for a later error", () => {
    const run = play(streaming({ pending: pending() }), [frame({ type: "start" })]);
    expect(run.state.pending).toMatchObject({ messageId: "local-1", accepted: true });
  });

  it("status shows the phase and its detail, and needs a string phase", () => {
    const sources = [{ title: "a", url: "u", snippet: "s" }];
    const run = play(streaming({ buffer: "so far", draft: { content: "", search_sources: sources } }), [
      frame({ type: "status", phase: "searching", detail: "weather" }),
    ]);
    expect(run.state.draft).toEqual({
      content: "so far", search_sources: sources, status: "searching", statusDetail: "weather", statusStartedAt: NOW,
    });
    const blank = play(run.state, [frame({ type: "status", phase: "thinking", detail: "" }), frame({ type: "status" })]);
    expect(blank.state.draft).toMatchObject({ status: "thinking", statusDetail: undefined });
    expect(cues(blank.commands)).toEqual(["activity", "activity"]);
  });

  it("a step keeps its start when sent again, and starts as long ago as the server says", () => {
    const thinking = play(streaming(), [frame({ type: "status", phase: "thinking", elapsed_ms: 4_000 })]);
    expect(thinking.state.draft?.statusStartedAt).toBe(NOW - 4_000);
    const again = play(thinking.state, [frame({ type: "status", phase: "thinking", elapsed_ms: 9_000 })]);
    expect(again.state.draft?.statusStartedAt).toBe(NOW - 4_000);
    const next = play(again.state, [frame({ type: "status", phase: "searching" })]);
    expect(next.state.draft?.statusStartedAt).toBe(NOW);
  });

  it("tokens build the reply, clear the status and mark the first token", () => {
    const run = play(streaming({ pending: pending(), draft: { content: "", status: "searching" } }), [
      frame({ type: "token", content: "Hel" }, "turn-9"),
      frame({ type: "token" }),
      frame({ type: "token", content: "lo" }),
    ]);
    expect(run.state.pending).toBeNull();
    expect(run.of("first_token")[0]).toEqual({ type: "first_token", turnId: "turn-9", frame: "token" });
    expect(run.state.buffer).toBe("Hello");
    expect(run.state.draft).toEqual({ content: "Hello", search_sources: undefined, status: undefined, statusDetail: undefined });
  });

  it("reasoning and unknown frames change nothing", () => {
    const start = streaming();
    const run = play(start, ["reasoning", "pong", "constructor", "toString", "__proto__"].map((type) => frame({ type })), [bubble]);
    expect(run.commands).toEqual([]);
    expect(run.state).toEqual(start);
  });

  it("stream_end starts finalizing and names the resolved model", () => {
    const run = play(streaming({ pending: pending() }), [frame({ type: "stream_end" }), frame({ type: "stream_end", resolved_model: "smart-chat" })], [bubble]);
    expect(run.state).toMatchObject({ phase: "finalizing", pending: null });
    expect(run.messages[0].model).toBe("smart-chat");
  });

  it("stream_end drops a label left over from the reply's last step", () => {
    const run = play(streaming({ buffer: "Done", draft: { content: "Done", status: "checking", statusStartedAt: NOW } }), [
      frame({ type: "stream_end" }),
    ]);
    expect(run.state.phase).toBe("finalizing");
    expect(run.state.draft).toEqual({ content: "Done", search_sources: undefined });
    expect(run.of("outcome")).toEqual([{ type: "outcome", outcome: "send_ready" }]);
  });

  it("done settles the turn, merges the reply and announces the first reply once", () => {
    const run = play(streaming({
      phase: "finalizing", buffer: "Hello there", draft: { content: "Hello there" }, pending: pending(),
      regenerateBackup: bubble, regenerating: true, ttftTurnId: "local-1", sendingMessageId: "local-1",
    }), [
      frame({ type: "done", message_id: "m-1", final_content: "Hello there!", resolved_model: "smart-chat" }),
    ], [bubble]);
    expect(run.state).toMatchObject({
      phase: "idle", pending: null, regenerating: false, regenerateBackup: null, ttftTurnId: null,
      sendingMessageId: null, buffer: "", draft: null, firstReply: true,
    });
    expect(cues(run.commands)).toEqual(["complete"]);
    expect(run.of("announce")).toEqual([{ type: "announce", key: "chat.reply_ready" }]);
    expect(run.messages).toEqual([expect.objectContaining({ id: "m-1", content: "Hello there!", model: "smart-chat" })]);
    expect(run.of("first_reply")).toHaveLength(1);
    expect(play(run.state, [frame({ type: "done", message_id: "m-2", final_content: "again" })]).of("first_reply")).toEqual([]);
  });

  it("done after Stop reconciles the kept bubble without the reply cue", () => {
    const kept = answer("streamed-1", "Hel");
    const run = play(idle({ stoppedStreamedId: "streamed-1" }), [
      frame({ type: "done", message_id: "m-1", final_content: "Hello", completion: "user_stop" }),
    ], [kept]);
    expect(run.state.stoppedStreamedId).toBeNull();
    expect(cues(run.commands)).toEqual([]);
    expect(run.of("announce")).toEqual([]);
    expect(run.messages).toEqual([expect.objectContaining({ id: "m-1", content: "Hello", generationStopped: true })]);
  });

  it("done reports a to-do change and the day's usage", () => {
    const usage = { used_tokens: 81_000, daily_limit: 100_000 };
    const run = play(streaming(), [frame({ type: "done", message_id: "m-1", final_content: "Added", todos_changed: true, usage })], [bubble]);
    expect(run.of("todos_changed")).toHaveLength(1);
    expect(run.of("usage")).toEqual([{ type: "usage", usage }]);
  });

  it("related_prompts attaches follow-ups to their message only", () => {
    const reply = answer("m-1", "Hi");
    const run = play(idle(), [frame({ type: "related_prompts", message_id: "m-1", prompts: ["One?", " ", 3, "Two?", "Three?", "Four?"] })], [reply]);
    expect(run.messages[0].related_prompts).toEqual(["One?", "Two?", "Three?"]);
    const none = play(idle(), [frame({ type: "related_prompts", prompts: ["Lost?"] }), frame({ type: "related_prompts", message_id: "m-1", prompts: [] })]);
    expect(none.commands).toEqual([]);
  });
});

describe("errors", () => {
  it("a busy turn queues the unsaved send under Retry and reports its reason", () => {
    const turn = pending();
    const user: Message = { id: "local-1", role: "user", content: "hello", model: null, created_at: "t" };
    const run = play(streaming({ pending: turn, ttftTurnId: "local-1", regenerating: true }), [
      frame({ type: "error", code: "busy", message: "Busy" }, null),
    ], [user, bubble]);
    expect(cues(run.commands)).toEqual(["error"]);
    expect(run.of("clear_ttft")).toEqual([{ type: "clear_ttft", turnId: "local-1" }]);
    expect(headRejectedSend(run.state)).toMatchObject({ messageId: "local-1", reason: "send_rejected" });
    expect(run.state).toMatchObject({ pending: null, ttftTurnId: null, regenerating: false, phase: "idle" });
    expect(run.messages).toEqual([]);
    expect(run.of("report_error")).toEqual([{ type: "report_error", message: "Busy", key: "chat.error_generic", code: "send_rejected" }]);
  });

  it("a rejected attachment waits under its own reason", () => {
    const run = play(streaming({ pending: pending() }), [frame({ type: "error", code: "attachment_rejected", message: "Too big" }, "turn-1")], [bubble]);
    expect(run.of("clear_ttft")).toEqual([{ type: "clear_ttft", turnId: "turn-1" }]);
    expect(headRejectedSend(run.state)?.reason).toBe("attachment_rejected");
    expect(run.of("report_error")[0]).toMatchObject({ message: "Too big", code: "attachment_rejected" });
  });

  it.each<[{ code?: string; message: string }, boolean, "send_rejected" | null]>([
    // Regression: every code-less error offered Regenerate, which re-answered the
    // previous message when this one was never saved.
    [{ message: "Redis down" }, false, "send_rejected"],
    [{ code: "unavailable", message: "Restarting" }, false, "send_rejected"],
    [{ message: "Failed to save the response. Please retry." }, true, null],
    [{ code: "quota_exceeded", message: "Out of quota" }, false, null],
    [{ code: "model_unavailable", message: "Down" }, false, null],
  ])("error %o with user_message_saved=%s queues a resend: %s", (payload, saved, reason) => {
    const run = play(streaming({ pending: pending() }), [frame({ type: "error", user_message_saved: saved, ...payload })], [bubble]);
    expect(headRejectedSend(run.state)?.reason ?? null).toBe(reason);
    expect(run.of("report_error")[0]).toMatchObject({ message: payload.message, code: reason ?? payload.code });
  });

  it("a picture's daily limit is reported as the picture's, not the chat quota", () => {
    const run = play(streaming({ pending: pending() }), [frame({ type: "error", code: "daily_limit", feature: "image_generation", user_message_saved: true, message: "No more pictures" })], [bubble]);
    expect(run.of("report_error")[0]).toMatchObject({ message: "No more pictures", code: "image_daily_limit" });
  });

  it("consent_required opens the consent screen and keeps the message to resend", () => {
    const run = play(streaming({ pending: pending() }), [frame({ type: "error", code: "consent_required", user_message_saved: false, message: "Agree first" })], [bubble]);
    expect(run.of("consent_required")).toHaveLength(1);
    expect(headRejectedSend(run.state)?.reason).toBe("send_rejected");
  });

  it("keeps a partial reply as a stopped bubble that a late done reconciles", () => {
    const sources = [{ title: "a", url: "u", snippet: "s" }];
    const run = play(streaming({ draft: { content: "Half an ans", search_sources: sources } }), [frame({ type: "error", code: "unavailable" })], [bubble]);
    expect(run.messages).toEqual([expect.objectContaining({
      id: `streamed-${NOW}`, content: "Half an ans", search_sources: sources, generationStopped: true,
    })]);
    expect(run.state).toMatchObject({ stoppedStreamedId: `streamed-${NOW}`, draft: null });
    expect(run.of("report_error")[0]).toMatchObject({ key: "chat.error_generic", code: "unavailable" });
  });

  it("an error during Regenerate brings the previous answer back", () => {
    const old = answer("old", "old answer");
    const run = play(streaming({ draft: { content: "partial" }, regenerateBackup: old, regenerating: true }), [frame({ type: "error", message: "Nope" })], [bubble]);
    expect(run.messages).toEqual([old]);
    expect(run.state).toMatchObject({ regenerateBackup: null, regenerating: false, phase: "idle", draft: null });
    expect(run.of("report_error")[0]).toMatchObject({ message: "Nope", code: undefined });
  });
});

describe("a turn from send to the end", () => {
  const send = (content: string, extra: Partial<Extract<ChatTurnEvent, { type: "send" }>> = {}): ChatTurnEvent =>
    ({ type: "send", content, clientMessageId: "name-1", ...extra });

  it("sends, streams and lands the reply", () => {
    const run = play(idle(), [
      send("hi"),
      { type: "send_dispatched" },
      frame({ type: "start" }),
      frame({ type: "token", content: "Hey" }, `local-${NOW}-1`),
      frame({ type: "stream_end" }),
      frame({ type: "done", message_id: "m-1", final_content: "Hey!" }),
    ]);
    expect(run.messages.map((m) => [m.id, m.content])).toEqual([[`local-${NOW}-1`, "hi"], ["m-1", "Hey!"]]);
    expect(run.state).toMatchObject({ phase: "idle", pending: null, attempt: 1, ttftTurnId: null });
    // Each frame asks for the activity cue; the cue gate plays it once a turn.
    expect(cues(run.commands)).toEqual(["reset", "activity", "activity", "complete"]);
  });

  it("shows reading files at once for a send with attachments", () => {
    const run = play(idle(), [send("look", { options: { attachmentIds: ["a1"] } })]);
    expect(run.state.draft).toEqual({ content: "", status: "reading_files" });
  });

  it("Stop keeps what streamed, ignores late deltas, and a late done names the kept bubble", () => {
    const run = play(idle(), [
      send("hi"),
      frame({ type: "start" }),
      frame({ type: "token", content: "Partial" }),
      { type: "stop" },
      frame({ type: "token", content: " more" }),
      frame({ type: "done", message_id: "m-1", final_content: "Partial more and more", completion: "user_stop" }),
    ]);
    expect(run.of("abort_sse")).toHaveLength(1);
    expect(run.of("cancel_socket")).toEqual([{ type: "cancel_socket", streamedChars: 7 }]);
    expect(run.messages.at(-1)).toMatchObject({ id: "m-1", content: "Partial more and more", generationStopped: true });
    expect(run.state.stoppedStreamedId).toBeNull();
  });

  it.each([
    ["the model picker's start", [{ type: "regenerate_ui", messages: [bubble] }]],
    ["the regenerate itself", [{ type: "regenerate", messages: [bubble] }]],
    ["both, in order", [{ type: "regenerate_ui", messages: [bubble] }, { type: "regenerate", messages: [bubble] }]],
  ] as [string, ChatTurnEvent[]][])("refuses %s while a reply streams, leaving that reply alone", (_label, events) => {
    const run = play(streaming({ buffer: "Half an answer", attempt: 4 }), events, [bubble]);
    expect(run.commands).toEqual([]);
    expect(run.messages).toEqual([bubble]);
    expect(run.state).toMatchObject({ phase: "streaming", buffer: "Half an answer", attempt: 4, regenerating: false });
  });

  it("runs the regenerate the model picker opened", () => {
    const old = answer("old", "old answer");
    const run = play(idle(), [{ type: "regenerate_ui", messages: [old] }, { type: "regenerate", messages: [old] }], [old]);
    expect(run.state).toMatchObject({ phase: "streaming", regenerating: true });
    expect(run.of("pop_for_regenerate")).toHaveLength(1);
  });

  it("Stop with nothing streamed during Regenerate restores the old answer", () => {
    const old = answer("old", "old answer");
    const run = play(idle(), [{ type: "regenerate_ui", messages: [old] }, { type: "stop" }], [old]);
    expect(run.messages).toEqual([old]);
    expect(run.state).toMatchObject({ phase: "idle", regenerating: false, regenerateBackup: null });
  });

  it("a send after Stop drops the socket that may still carry the stopped turn", () => {
    const run = play(idle({ stoppedStreamedId: "streamed-1" }), [send("again")]);
    expect(run.of("drop_socket")).toHaveLength(1);
    expect(run.state.stoppedStreamedId).toBeNull();
  });

  it("Retry uses up the rejected send only once sending begins", () => {
    const rejectedFirst = play(streaming({ pending: pending() }), [frame({ type: "error", code: "busy" })], [bubble]);
    const rejected = headRejectedSend(rejectedFirst.state)!;
    const retrying = play(rejectedFirst.state, [send(rejected.content, { retrying: rejected })]);
    expect(headRejectedSend(retrying.state)).toBe(rejected);
    const dispatched = play(retrying.state, [{ type: "send_dispatched", retrying: rejected }]);
    expect(headRejectedSend(dispatched.state)).toBeNull();
    expect(dispatched.state.pending).toMatchObject({ retryingRejected: true, dispatched: true });
  });

  it("a new chat or account resets the turn; only an account change drops Retry", () => {
    const rejected = play(streaming({ pending: pending() }), [frame({ type: "error", code: "busy" })], [bubble]).state;
    const otherChat = play(rejected, [{ type: "view_changed", chatId: "chat-2", session: 0 }]);
    expect(otherChat.state).toMatchObject({ chatId: "chat-2", phase: "idle", firstReply: false });
    expect(otherChat.state.rejected.get("chat-1")).toHaveLength(1);
    const otherAccount = play(otherChat.state, [{ type: "view_changed", chatId: "chat-1", session: 1 }]);
    expect(headRejectedSend(otherAccount.state)).toBeNull();
  });
});

describe("dropped connections", () => {
  const signal = (reason: "disconnect" | "closed_unread" | "first_event_timeout" | "unresponsive", duringTurn = true) =>
    ({ reason, duringTurn }) as Extract<ChatTurnEvent, { type: "socket_fallback" }>["signal"];
  const dropped = (s: Extract<ChatTurnEvent, { type: "socket_fallback" }>["signal"]): ChatTurnEvent =>
    ({ type: "socket_fallback", transport: socket, signal: s });

  it("replays a send the server closed unread, once, while the fallback is armed", async () => {
    const retry = jest.fn(async () => undefined);
    const run = play(streaming({ authFallback: { transport: socket, retry } }), [dropped(signal("closed_unread"))]);
    expect(run.of("retry_fallback")).toHaveLength(1);
    expect(run.state.authFallback).toBeNull();
  });

  it("replays over SSE when the server refuses the socket's auth, else applies the refusal", () => {
    const retry = jest.fn(async () => undefined);
    const armed = play(streaming({ authFallback: { transport: socket, retry } }), [
      { type: "socket_fallback", transport: socket, signal: { reason: "unauthorized", duringTurn: true, payload: { type: "error" } } },
    ]);
    expect(armed.of("retry_fallback")).toHaveLength(1);
    const refusal = play(streaming({ pending: pending() }), [
      { type: "socket_fallback", transport: socket, signal: { reason: "unauthorized", duringTurn: true, payload: { type: "error", code: "unauthorized", message: "Sign in" } } },
    ], [bubble]);
    expect(refusal.of("report_error")[0]).toMatchObject({ message: "Sign in" });
    expect(refusal.state.phase).toBe("idle");
  });

  it("keeps the bubble when no event came, and never replays that uncertain turn", () => {
    const run = play(streaming({ pending: pending(), ttftTurnId: "local-1" }), [dropped(signal("first_event_timeout"))], [bubble]);
    expect(run.of("retry_fallback")).toEqual([]);
    expect(headRejectedSend(run.state)).toBeNull();
    expect(run.state).toMatchObject({ phase: "idle", pending: null });
    expect(run.of("report_error")[0]).toMatchObject({ key: "chat.error_unreachable" });
  });

  it("replays a named message when a probe finds its socket dead before start", () => {
    const retry = jest.fn(async () => undefined);
    const run = play(streaming({ pending: pending(), authFallback: { transport: socket, retry, idempotent: true } }),
      [dropped(signal("unresponsive"))], [bubble]);
    expect(run.of("retry_fallback")).toHaveLength(1);
    expect(run.of("report_error")).toEqual([]);
  });

  it("gives up an unnamed send, a regenerate, on a dead socket instead of replaying it", () => {
    const retry = jest.fn(async () => undefined);
    const old = answer("m-1", "Old answer");
    const run = play(streaming({ regenerateBackup: old, authFallback: { transport: socket, retry } }),
      [dropped(signal("unresponsive"))], [bubble]);
    expect(run.of("retry_fallback")).toEqual([]);
    expect(run.messages).toEqual([old]);
    expect(run.of("report_error")[0]).toMatchObject({ key: "chat.error_unreachable" });
  });

  it("follows the earlier send on duplicate, for minutes, instead of asking for a second turn", () => {
    const run = play(streaming({ pending: pending({ clientMessageId: "c-1" }) }), [frame({ type: "duplicate" })], [bubble]);
    const [follow] = run.of("follow_dropped_turn");
    expect(follow.follow).toMatchObject({ via: "duplicate", pending: expect.objectContaining({ messageId: "local-1" }) });
    expect(follow.polls).toBe(DUPLICATE_TURN_POLLS);
    expect(follow.pollMs?.(0)).toBe(duplicateTurnPollMs(0));
    expect(run.state.pending).toBeNull();
  });

  it("ignores a duplicate that arrives after Stop", () => {
    const run = play(idle({ pending: pending() }), [frame({ type: "duplicate" })]);
    expect(run.of("follow_dropped_turn")).toEqual([]);
  });

  it("follows a turn the server took until the reply lands", () => {
    const followed = play(streaming({ pending: pending({ accepted: true }) }), [dropped(signal("disconnect"))], [bubble]);
    const [follow] = followed.of("follow_dropped_turn");
    expect(follow.follow).toMatchObject({ via: "socket" });
    const page = [answer("m-1", "Landed")];
    const landed = play(followed.state, [{ type: "dropped_turn", follow: follow.follow, result: { state: "answered", page } }], [bubble]);
    expect(landed.messages).toEqual(page);
    expect(cues(landed.commands)).toEqual(["complete"]);
    expect(landed.of("first_reply")).toHaveLength(1);
  });

  it("offers Retry for a send a reload shows is not in the chat", () => {
    const followed = play(streaming({ pending: pending({ accepted: true }) }), [dropped(signal("disconnect"))], [bubble]);
    const [follow] = followed.of("follow_dropped_turn");
    const missing = play(followed.state, [{ type: "dropped_turn", follow: follow.follow, result: { state: "missing", page: null } }], [bubble]);
    expect(headRejectedSend(missing.state)?.reason).toBe("send_rejected");
    expect(missing.of("report_error")[0]).toMatchObject({ key: "chat.error_unreachable", code: "send_rejected" });
  });

  it("keeps a partial reply when a socket drops before the server took the send", () => {
    const run = play(streaming({ buffer: "Half", draft: { content: "Half" } }), [dropped(signal("disconnect"))], [bubble]);
    // Streamed text means the server took it: the turn is followed, not settled.
    expect(run.of("follow_dropped_turn")).toHaveLength(1);
    const lost = play(streaming(), [dropped(signal("disconnect"))], [bubble]);
    expect(lost.messages).toEqual([]);
    expect(lost.of("report_error")[0]).toMatchObject({ key: "chat.error_connection_lost" });
  });

  it("an SSE failure keeps what streamed; a cancelled one stays out of Retry", () => {
    const partial = play(streaming({ draft: { content: "So far" }, pending: pending() }), [
      { type: "send_failed", error: new Error("network"), ttftTurnId: "local-1" },
    ], [bubble]);
    expect(partial.messages).toEqual([expect.objectContaining({ id: `streamed-${NOW}`, content: "So far" })]);
    const aborted = Object.assign(new Error("aborted"), { name: "AbortError" });
    const cancelled = play(streaming({ pending: pending() }), [{ type: "send_failed", error: aborted, ttftTurnId: null }], [bubble]);
    expect(headRejectedSend(cancelled.state)).toBeNull();
    const unsent = play(streaming({ pending: pending() }), [{ type: "send_failed", error: new Error("offline"), ttftTurnId: null }], [bubble]);
    expect(headRejectedSend(unsent.state)?.reason).toBe("send_rejected");
  });

  it.each([
    ["unavailable", "Service temporarily unavailable."],
    ["consent_required", "Agree first"],
  ])("an SSE refusal coded %s says what the socket's error frame says", (code, words) => {
    const old = answer("old", "old answer");
    const refused = new ApiRequestError(503, JSON.stringify({ detail: { code, message: words } }));
    const refusal = frame({ type: "error", code, message: words, user_message_saved: false });
    /** The line the chat shows (useChatErrorHandlers). */
    const line = (run: ReturnType<typeof play>) => run.of("report_error").map((report) =>
      resolveChatError({ message: report.message ?? report.key, code: report.code, isPaid: false, t: (key) => key }).message);
    const regenerate = (event: ChatTurnEvent) => play(streaming({ regenerateBackup: old, regenerating: true }), [event], [bubble]);
    const send = (event: ChatTurnEvent) => play(streaming({ pending: pending() }), [event], [bubble]);

    expect(line(regenerate({ type: "regenerate_failed", error: refused }))).toEqual(line(regenerate(refusal)));
    expect(line(send({ type: "send_failed", error: refused, ttftTurnId: null }))).toEqual(line(send(refusal)));
    expect(line(regenerate(refusal))).toEqual([code === "unavailable" ? "common.service_unavailable" : words]);
  });

  // The request limiter's 429, the chat stream's own and the socket's limit frame: each
  // named no code, and said "Couldn't reach the server" or showed the server's English.
  const limited = (message: string) => new ApiRequestError(429, JSON.stringify({ detail: { code: "rate_limited", message } }));
  it.each<[string, ChatTurnEvent]>([
    ["the request limiter", { type: "regenerate_failed", error: limited("Too many requests. Please slow down.") }],
    ["the chat stream's limit", { type: "regenerate_failed", error: limited("Too many chat requests. Try again shortly.") }],
    ["the socket's limit", frame({ type: "error", code: "rate_limited", message: "Too many requests. Try again shortly.", user_message_saved: false })],
  ])("a Regenerate refused by %s says so, not that the server was unreachable", (_name, event) => {
    const old = answer("old", "old answer");
    const run = play(streaming({ regenerateBackup: old, regenerating: true }), [event], [bubble]);
    const lines = run.of("report_error").map((report) =>
      resolveChatError({ message: report.message ?? report.key, code: report.code, isPaid: false, t: (key) => key }).message);
    expect(lines).toEqual(["chat.rate_limited"]);
    expect(run.messages).toEqual([old]);
  });

  it("a failed Regenerate keeps what streamed, or brings the old answer back", () => {
    const old = answer("old", "old answer");
    const restored = play(streaming({ regenerateBackup: old, regenerating: true }), [{ type: "regenerate_failed" }], [bubble]);
    expect(restored.messages).toEqual([old]);
    const kept = play(streaming({ regenerateBackup: old, draft: { content: "New" } }), [{ type: "regenerate_failed" }], [bubble]);
    expect(kept.state.regenerateBackup).toBeNull();
    expect(kept.messages).toEqual([expect.objectContaining({ content: "New" })]);
  });
});

describe("thread edits", () => {
  const older = answer("older", "older answer");

  it.each([
    ["at rest", idle()],
    ["while a reply streams", streaming({ draft: { content: "Hal" } })],
    ["while it finalizes", idle({ phase: "finalizing" })],
  ])("an edit %s changes the list only, in the order edits arrive", (_name, state) => {
    const run = play(state, [
      { type: "thread_edit", source: "older_page", update: (rows) => [older, ...rows] },
      { type: "thread_edit", source: "feedback", update: (rows) => rows.map((row) => ({ ...row, feedback: "up" as const })) },
    ], [bubble]);
    expect(run.messages).toEqual([{ ...older, feedback: "up" }, { ...bubble, feedback: "up" }]);
    expect(run.state).toEqual(state);
    expect(run.commands.map((command) => command.type)).toEqual(["messages", "messages"]);
  });

  it("a new list replaces the thread as it is", () => {
    const run = play(idle(), [{ type: "thread_edit", source: "view_cleared", update: [] }], [bubble, older]);
    expect(run.messages).toEqual([]);
  });

  // 2026-11-01: a picture that finished after the user opened another chat landed in that chat.
  const picture = answer("saved-image", "image");
  const pictureFor = (chatId: string): ChatTurnEvent =>
    ({ type: "thread_edit", source: "image_turn", update: (rows) => [...rows, picture], chatId });
  const viewOf = (chatId: string | null, session = 0): ChatTurnEvent => ({ type: "view_changed", chatId, session });

  it.each([
    ["another chat", [viewOf("chat-2")]],
    ["a new chat", [viewOf(null)]],
    ["another chat, then a new one", [viewOf("chat-2"), viewOf(null)]],
  ])("an edit for a chat the user left waits for it, in %s", (_name, moves) => {
    const run = play(idle(), [...moves, pictureFor("chat-1")], [older]);
    expect(run.messages).toEqual([older]);
    expect(run.of("messages")).toHaveLength(0);
    // Back in its chat (its page painted first), the edit lands once.
    const back = play(run.state, [{ type: "thread_edit", source: "cached_paint", update: [bubble] }, viewOf("chat-1"), viewOf("chat-2"), viewOf("chat-1")]);
    expect(back.messages).toEqual([bubble, picture]);
    expect(back.state.heldEdits.size).toBe(0);
  });

  it("an edit for the chat on screen lands at once", () => {
    expect(play(idle(), [pictureFor("chat-1")]).messages).toEqual([picture]);
  });

  it("an edit for the chat a new view is becoming lands when the view names it", () => {
    // The new chat's id reaches the turn a render after the picture learns it.
    const run = play(idle({ chatId: null }), [pictureFor("new-1"), viewOf("new-1")]);
    expect(run.messages).toEqual([picture]);
  });

  it("held edits never reach another account", () => {
    const run = play(idle(), [viewOf("chat-2"), pictureFor("chat-1"), viewOf("chat-1", 1)]);
    expect(run.messages).toEqual([]);
  });
});
