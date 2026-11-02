import { reportChatTurnOutcome } from "@/features/chat/model/latencyReporter";
import { CHAT_EVENT_SAMPLE_RATE } from "@/features/chat/model/chatEventSample";
import { initialChatTurnState, type ChatTurnState } from "@/features/chat/model/chatTurnCore";
import { reduceChatTurn } from "@/features/chat/model/chatTurnState";
import type { ChatSsePayload } from "@/features/chat/model/sse";
import {
  beginTurnOutcome,
  completionFromDone,
  noteTurnActivity,
  noteTurnSendReady,
  noteTurnToken,
  reportTurnOutcome,
  sendReadyBucket,
  turnOutcomeProperties,
} from "@/features/chat/model/turnOutcome";

jest.mock("@/features/chat/model/latencyReporter", () => ({
  reportChatTurnOutcome: jest.fn(async () => undefined),
}));
// The turn announces a finished reply; nothing here reaches that.
jest.mock("react-native", () => ({ AccessibilityInfo: { announceForAccessibility: jest.fn() } }));

const report = reportChatTurnOutcome as jest.Mock;
const settle = () => new Promise<void>((done) => setImmediate(() => done()));

describe("chat_turn_outcome (O10.1)", () => {
  beforeEach(async () => {
    // Close a turn an earlier case left open.
    reportTurnOutcome("complete");
    await settle();
    report.mockClear();
    // Every turn in the sample unless a case says otherwise.
    jest.spyOn(Math, "random").mockReturnValue(0);
  });
  afterEach(() => {
    jest.restoreAllMocks();
  });

  it("reports one turn in five (NET-15)", async () => {
    jest.spyOn(Math, "random").mockReturnValue(CHAT_EVENT_SAMPLE_RATE);
    beginTurnOutcome();
    reportTurnOutcome("complete");
    await settle();
    expect(report).not.toHaveBeenCalled();
    jest.spyOn(Math, "random").mockReturnValue(CHAT_EVENT_SAMPLE_RATE - 0.01);
    beginTurnOutcome();
    reportTurnOutcome("complete");
    await settle();
    expect(report).toHaveBeenCalledTimes(1);
  });

  it("names the first tool the turn showed and a clean finish", async () => {
    beginTurnOutcome();
    noteTurnActivity("composing");
    noteTurnActivity("searching");
    noteTurnActivity("calculating");
    reportTurnOutcome(completionFromDone(undefined));
    await settle();
    expect(report).toHaveBeenCalledWith({
      completion: "complete", error_code: "none", tool: "searching", send_ready_bucket: "none",
    });
  });

  it("does not count the photo found above a finished reply as the turn's tool", async () => {
    beginTurnOutcome();
    noteTurnActivity("composing");
    noteTurnActivity("answer_photo");
    noteTurnActivity("finishing");
    reportTurnOutcome(completionFromDone(undefined));
    await settle();
    expect(report).toHaveBeenCalledWith({
      completion: "complete", error_code: "none", tool: "none", send_ready_bucket: "none",
    });
  });

  it("reports a turn once, whatever frames follow", async () => {
    beginTurnOutcome();
    reportTurnOutcome("stopped");
    reportTurnOutcome(completionFromDone("user_stop"));
    reportTurnOutcome("error", "busy");
    await settle();
    expect(report).toHaveBeenCalledTimes(1);
    expect(report).toHaveBeenCalledWith({
      completion: "stopped", error_code: "none", tool: "none", send_ready_bucket: "none",
    });
  });

  it("keeps only the server's own error codes; anything else is other", () => {
    beginTurnOutcome();
    expect(turnOutcomeProperties("error", "model_unavailable").error_code).toBe("model_unavailable");
    expect(turnOutcomeProperties("error", "That model isn't responding").error_code).toBe("other");
    expect(turnOutcomeProperties("error").error_code).toBe("other");
    expect(turnOutcomeProperties("complete", "busy").error_code).toBe("none");
  });

  // The turn's own failures, consent and a picture's refusals were counted as "other".
  it.each([
    "consent_required", "daily_limit", "content_blocked", "not_found", "failed", "reply_not_saved", "server_restarting",
  ])("counts a turn that failed with %s by its code", (code) => {
    beginTurnOutcome();
    expect(turnOutcomeProperties("error", code).error_code).toBe(code);
  });

  it("counts a picture's refusal by the frame's code, not the phone's wording", () => {
    const state: ChatTurnState = { ...initialChatTurnState("chat-1", 0), phase: "streaming" };
    const payload: ChatSsePayload = { type: "error", code: "daily_limit", feature: "image_generation", message: "x" };
    const { commands } = reduceChatTurn(state, { type: "frame", payload }, 0);
    expect(commands).toContainEqual({ type: "outcome", outcome: "report", completion: "error", code: "daily_limit" });
    expect(commands).toContainEqual(expect.objectContaining({ type: "report_error", code: "image_daily_limit" }));
  });

  it("reads the done frame's completion", () => {
    expect(completionFromDone("user_stop")).toBe("stopped");
    expect(completionFromDone("interrupted")).toBe("interrupted");
    expect(completionFromDone("complete")).toBe("complete");
  });

  it("never reports a turn that did not start", async () => {
    reportTurnOutcome("error", "busy");
    await settle();
    expect(report).not.toHaveBeenCalled();
  });

  it.each([
    [null, "none"],
    [0, "lt100"],
    [99, "lt100"],
    [100, "100_249"],
    [250, "250_499"],
    [500, "500_999"],
    [1_000, "1000_1999"],
    [2_000, "2000_plus"],
  ])("buckets last token -> Send ready of %p ms as %s", (elapsedMs, bucket) => {
    expect(sendReadyBucket(elapsedMs)).toBe(bucket);
  });

  it("measures last token -> Send ready from the turn's frames, once per turn", async () => {
    const now = jest.spyOn(Date, "now").mockReturnValue(1_000);
    let state: ChatTurnState = { ...initialChatTurnState("chat-1", 0), phase: "streaming" };
    // The turn's metric commands, as chatTurnEffects runs them.
    const frame = (payload: ChatSsePayload) => {
      const next = reduceChatTurn(state, { type: "frame", payload }, Date.now());
      state = next.state;
      for (const command of next.commands) {
        if (command.type !== "outcome") continue;
        if (command.outcome === "token") noteTurnToken();
        if (command.outcome === "send_ready") noteTurnSendReady();
      }
    };
    beginTurnOutcome();
    frame({ type: "token", content: "Hel" });
    now.mockReturnValue(1_050);
    frame({ type: "token", content: "lo" });
    now.mockReturnValue(1_350);
    frame({ type: "stream_end" });
    // Saving from this frame on: a send now waits on it at once, not after a render.
    expect(state.phase).toBe("finalizing");
    now.mockReturnValue(9_000);
    noteTurnSendReady();
    expect(turnOutcomeProperties("complete").send_ready_bucket).toBe("250_499");
    now.mockRestore();
  });

  it("leaves Send ready unmeasured for a turn with no stream_end, or none before it", () => {
    beginTurnOutcome();
    noteTurnSendReady();
    expect(turnOutcomeProperties("error").send_ready_bucket).toBe("none");
    noteTurnToken();
    expect(turnOutcomeProperties("stopped").send_ready_bucket).toBe("none");
    // A new turn starts clean.
    noteTurnSendReady();
    beginTurnOutcome();
    expect(turnOutcomeProperties("complete").send_ready_bucket).toBe("none");
  });
});
