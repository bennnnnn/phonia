import { mergeDoneIntoMessages, buildDoneMergeInput, applyRelatedPrompts, applyStreamEndModel, parseChatWsPayload, relatedPromptsFromEvent, shouldIgnoreStoppedStreamEvent } from "@/features/chat/model/socketReduce";
import type { Message } from "@/lib/api";

describe("chatSocketReduce", () => {
  it("parseChatWsPayload parses tokens without recording TTFT", () => {
    expect(parseChatWsPayload('{"type":"token","content":"hi"}')).toEqual({
      type: "token",
      content: "hi",
    });
    expect(parseChatWsPayload("not-json")).toBeNull();
  });

  it("mergeDoneIntoMessages replaces streaming placeholder", () => {
    const prev: Message[] = [
      { id: "u1", role: "user", content: "Hello", model: null, created_at: "t" },
      {
        id: "streaming",
        renderKey: "stream-1",
        role: "assistant",
        content: "",
        model: null,
        created_at: "t",
      },
    ];
    const next = mergeDoneIntoMessages(prev, {
      finalId: "msg-1",
      messageId: "msg-1",
      draftContent: "Hi back",
    });
    expect(next).toHaveLength(2);
    expect(next[1].id).toBe("msg-1");
    expect(next[1].renderKey).toBe("stream-1");
    expect(next[1].content).toBe("Hi back");
  });

  it("mergeDoneIntoMessages drops empty streaming bubble without message_id", () => {
    const prev: Message[] = [
      { id: "streaming", role: "assistant", content: "", model: null, created_at: "t" },
    ];
    const next = mergeDoneIntoMessages(prev, {
      finalId: "x",
      draftContent: "   ",
    });
    expect(next).toHaveLength(0);
  });

  it("mergeDoneIntoMessages prefers final_content on streaming placeholder", () => {
    const prev: Message[] = [
      { id: "streaming", role: "assistant", content: "Intro\n```places", model: null, created_at: "t" },
    ];
    const next = mergeDoneIntoMessages(prev, {
      finalId: "msg-1",
      messageId: "msg-1",
      draftContent: "Intro\n```places",
      finalContent: "Intro\n\n```places\n[{\"name\":\"A\"}]\n```",
    });
    expect(next[0].content).toContain("```places");
  });

  it("mergeDoneIntoMessages appends assistant when streaming placeholder missing", () => {
    const prev: Message[] = [
      { id: "u1", role: "user", content: "Q", model: null, created_at: "t" },
      {
        id: "streamed-1",
        role: "assistant",
        content: "Partial",
        model: null,
        created_at: "t",
      },
    ];
    const next = mergeDoneIntoMessages(prev, {
      finalId: "msg-final",
      messageId: "msg-final",
      draftContent: "Partial",
      finalContent: "Partial plus more from server",
    });
    expect(next).toHaveLength(3);
    expect(next[2].id).toBe("msg-final");
    expect(next[2].content).toBe("Partial plus more from server");
    expect(next[1].content).toBe("Partial");
  });

  const stoppedBubble: Message[] = [
    { id: "u1", role: "user", content: "Q", model: null, created_at: "t" },
    {
      id: "streamed-100",
      role: "assistant",
      content: "Partial reply",
      model: null,
      created_at: "t",
      generationStopped: true,
    },
  ];

  it("mergeDoneIntoMessages reconciles stopped bubble in place (no duplicate)", () => {
    // S7.11: the server saves a stopped reply as the phone drew it, made safe.
    const next = mergeDoneIntoMessages(
      stoppedBubble,
      buildDoneMergeInput(
        {
          type: "done",
          message_id: "msg-server-1",
          final_content: "Partial reply",
          completion: "user_stop",
        },
        null,
        0,
        "streamed-100",
      ),
    );
    expect(next).toHaveLength(2);
    expect(next[1].id).toBe("msg-server-1");
    expect(next[1].content).toBe("Partial reply");
    expect(next[1].generationStopped).toBe(true);
  });

  it("a stopped answer never grows: a reply the server finished anyway keeps what the user saw", () => {
    // Regression: the stopped turn's done swapped in the server's text, with
    // tokens the phone dropped after Stop and a verified card added at finalize.
    const next = mergeDoneIntoMessages(
      stoppedBubble,
      buildDoneMergeInput(
        {
          type: "done",
          message_id: "msg-server-1",
          final_content: "Partial reply with server tail\n\n```answer\nverified: true\nx = 4\n```",
        },
        null,
        0,
        "streamed-100",
      ),
    );
    expect(next).toHaveLength(2);
    expect(next[1].id).toBe("msg-server-1");
    expect(next[1].content).toBe("Partial reply");
  });

  it("a stopped done without final_content keeps the bubble's text", () => {
    const next = mergeDoneIntoMessages(
      stoppedBubble,
      buildDoneMergeInput(
        { type: "done", message_id: "msg-server-1", completion: "user_stop" },
        null,
        0,
        "streamed-100",
      ),
    );
    expect(next[1].content).toBe("Partial reply");
  });

  it("mergeDoneIntoMessages removes stopped bubble when done is empty and has no message_id", () => {
    const prev: Message[] = [
      { id: "u1", role: "user", content: "Q", model: null, created_at: "t" },
      {
        id: "streamed-100",
        role: "assistant",
        content: "   ",
        model: null,
        created_at: "t",
      },
    ];
    const next = mergeDoneIntoMessages(prev, {
      finalId: "x",
      draftContent: "   ",
      stoppedStreamedId: "streamed-100",
    });
    expect(next).toHaveLength(1);
    expect(next[0].id).toBe("u1");
  });

  it("mergeDoneIntoMessages drops late done when stopped id is no longer present", () => {
    const prev: Message[] = [
      { id: "u1", role: "user", content: "Q", model: null, created_at: "t" },
    ];
    const next = mergeDoneIntoMessages(prev, {
      finalId: "msg-1",
      messageId: "msg-1",
      draftContent: "Late content",
      finalContent: "Late content",
      stoppedStreamedId: "streamed-100",
    });
    expect(next).toHaveLength(1);
    expect(next[0].id).toBe("u1");
  });

  describe("a done whose saved reply is already on screen", () => {
    const user: Message = { id: "u1", role: "user", content: "Q", model: null, created_at: "t" };
    const saved: Message = { id: "msg-1", role: "assistant", content: "A cat.", model: null, created_at: "t" };

    it("drops the typing placeholder instead of showing the reply twice", () => {
      const placeholder: Message = { id: "streaming", role: "assistant", content: "", model: null, created_at: "t" };
      const next = mergeDoneIntoMessages([user, saved, placeholder], buildDoneMergeInput(
        { type: "done", message_id: "msg-1", final_content: "A cat." }, { content: "A cat." },
      ));
      expect(next.map((m) => m.id)).toEqual(["u1", "msg-1"]);
      expect(next[1]).toBe(saved);
    });

    it("drops a stopped bubble the same way", () => {
      const stopped: Message = { id: "streamed-100", role: "assistant", content: "A c", model: null, created_at: "t" };
      const next = mergeDoneIntoMessages([user, saved, stopped], {
        finalId: "msg-1", messageId: "msg-1", draftContent: "", stoppedStreamedId: "streamed-100",
      });
      expect(next.map((m) => m.id)).toEqual(["u1", "msg-1"]);
    });

    it("does not append a second copy, and leaves the list as it was", () => {
      const prev = [user, saved];
      const next = mergeDoneIntoMessages(prev, { finalId: "msg-1", messageId: "msg-1", draftContent: "A cat." });
      expect(next).toBe(prev);
    });
  });

  it("a later related_prompts event stores the full questions", () => {
    const prev: Message[] = [
      { id: "u1", role: "user", content: "what is the force?", model: null, created_at: "t" },
      { id: "streaming", role: "assistant", content: "30 N", model: null, created_at: "t" },
    ];
    const prompts = [
      "Why is the force the product of mass and acceleration?",
      "What changes if this object is already moving?",
      "How do you find the acceleration from the force and the mass?",
    ];
    const done = mergeDoneIntoMessages(
      prev,
      buildDoneMergeInput(
        { type: "done", message_id: "msg-1", final_content: "30 N" },
        { content: "30 N" },
      ),
    );
    expect(done[1].related_prompts).toBeUndefined();
    const next = applyRelatedPrompts(done, "msg-1", prompts);
    expect(next[1].related_prompts).toEqual(prompts);
  });

  it("reads follow-up questions from the prompts field on the event", () => {
    const payload = parseChatWsPayload(
      JSON.stringify({
        type: "related_prompts",
        message_id: "msg-1",
        prompts: [
          "Why is the force the product of mass and acceleration?",
          "What changes if this object is already moving?",
        ],
      }),
    );
    expect(payload).not.toBeNull();
    expect(relatedPromptsFromEvent(payload!)).toEqual([
      "Why is the force the product of mass and acceleration?",
      "What changes if this object is already moving?",
    ]);
  });

  it("buildDoneMergeInput parses stream metadata", () => {
    const input = buildDoneMergeInput(
      {
        type: "done",
        message_id: "abc",
        resolved_model: "smart-chat",
        final_content: "Full text",
      },
      { content: "Full text" },
      123,
    );
    expect(input.finalId).toBe("abc");
    expect(input.model).toBe("smart-chat");
    expect(input.finalContent).toBe("Full text");
  });

  it("buildDoneMergeInput does not copy reasoning onto the settled message", () => {
    const input = buildDoneMergeInput(
      { type: "done", message_id: "abc" },
      { content: "Hi" },
    );
    expect(input).not.toHaveProperty("reasoning_preview");
  });

  it("buildDoneMergeInput passes stoppedStreamedId through", () => {
    const input = buildDoneMergeInput(
      { type: "done", message_id: "abc" },
      { content: "Hi" },
      123,
      "streamed-100",
    );
    expect(input.stoppedStreamedId).toBe("streamed-100");
  });

  it("maps interrupted completion onto generationStopped", () => {
    const input = buildDoneMergeInput(
      { type: "done", message_id: "abc", completion: "interrupted" },
      { content: "Partial" },
    );
    expect(input.generationStopped).toBe(true);
    const prev: Message[] = [
      { id: "streaming", role: "assistant", content: "Partial", model: null, created_at: "" },
    ];
    const next = mergeDoneIntoMessages(prev, input);
    expect(next[0].generationStopped).toBe(true);
  });

  it("does not mark a complete done as generationStopped", () => {
    const input = buildDoneMergeInput(
      { type: "done", message_id: "abc" },
      { content: "Full" },
    );
    expect(input.generationStopped).toBe(false);
  });

  it("mergeDoneIntoMessages stores resolved model on assistant message", () => {
    const prev: Message[] = [
      { id: "u1", role: "user", content: "Hi", model: null, created_at: "" },
      { id: "streaming", role: "assistant", content: "Hello", model: null, created_at: "" },
    ];
    const next = mergeDoneIntoMessages(prev, {
      finalId: "a1",
      messageId: "a1",
      draftContent: "Hello",
      model: "free-chat",
    });
    expect(next[1].model).toBe("free-chat");
  });

  it("applyStreamEndModel patches streaming placeholder", () => {
    const prev: Message[] = [
      { id: "streaming", role: "assistant", content: "Hi", model: null, created_at: "" },
    ];
    const next = applyStreamEndModel(prev, "smart-chat");
    expect(next[0].model).toBe("smart-chat");
  });

  it("shouldIgnoreStoppedStreamEvent drops late starts and deltas after Stop, not done/error", () => {
    expect(shouldIgnoreStoppedStreamEvent("token", false)).toBe(true);
    expect(shouldIgnoreStoppedStreamEvent("status", false)).toBe(true);
    expect(shouldIgnoreStoppedStreamEvent("reasoning", false)).toBe(true);
    expect(shouldIgnoreStoppedStreamEvent("stream_end", false)).toBe(true);
    expect(shouldIgnoreStoppedStreamEvent("token", true)).toBe(false);
    expect(shouldIgnoreStoppedStreamEvent("start", false)).toBe(true);
    expect(shouldIgnoreStoppedStreamEvent("start", true)).toBe(false);
    expect(shouldIgnoreStoppedStreamEvent("done", false)).toBe(false);
    expect(shouldIgnoreStoppedStreamEvent("error", false)).toBe(false);
  });
});

describe("done event shapes (today's strings, ES-45's typed fields)", () => {
  const sources = [{ title: "AP News", url: "https://apnews.com/a", snippet: "Story text." }];
  const parseDone = (fields: Record<string, unknown>) =>
    parseChatWsPayload(JSON.stringify({ type: "done", message_id: "m1", ...fields }));

  it("reads search_sources as JSON text or as an array", () => {
    expect(parseDone({ search_sources: JSON.stringify(sources) })?.search_sources).toEqual(sources);
    expect(parseDone({ search_sources: sources })?.search_sources).toEqual(sources);
  });

  it.each([undefined, "", "[]", [], "not json", { title: "x" }])(
    "leaves search_sources out for %j",
    (search_sources) => {
      expect(parseDone({ search_sources })).not.toHaveProperty("search_sources");
    },
  );

  it.each<[Record<string, unknown>, boolean]>([
    [{ todos_sync: "1" }, true],
    [{ todos_changed: true }, true],
    [{}, false],
    [{ todos_sync: "0" }, false],
    [{ todos_changed: false }, false],
  ])("reads %j as todos_changed %s", (fields, changed) => {
    const payload = parseDone(fields);
    expect(payload?.todos_changed === true).toBe(changed);
    expect(payload).not.toHaveProperty("todos_sync");
  });

  it("reads the day's usage the server sends as strings", () => {
    const payload = parseDone({ used_tokens: "81000", daily_limit: "100000" });
    expect(payload?.usage).toEqual({ used_tokens: 81_000, daily_limit: 100_000 });
    expect(payload).not.toHaveProperty("used_tokens");
    expect(payload).not.toHaveProperty("daily_limit");
    expect(parseDone({ used_tokens: 0, daily_limit: 5 })?.usage).toEqual({ used_tokens: 0, daily_limit: 5 });
  });

  it.each<Record<string, unknown>>([
    {},
    { used_tokens: "81000" },
    { daily_limit: "100000" },
    { used_tokens: "", daily_limit: "100000" },
    { used_tokens: "lots", daily_limit: "100000" },
    { used_tokens: "-1", daily_limit: "100000" },
    { used_tokens: "1.5", daily_limit: "100000" },
    { used_tokens: "10", daily_limit: "0" },
    { used_tokens: true, daily_limit: "100000" },
  ])("leaves usage out for %j", (fields) => {
    expect(parseDone(fields)).not.toHaveProperty("usage");
  });

  it("hands either shape's sources to the done merge", () => {
    for (const search_sources of [JSON.stringify(sources), sources]) {
      const payload = parseDone({ search_sources });
      expect(buildDoneMergeInput(payload!, { content: "Answer" }).search_sources).toEqual(sources);
    }
    expect(buildDoneMergeInput(parseDone({})!, { content: "Answer" }).search_sources).toBeUndefined();
  });

  it("drops a frame that is not an object", () => {
    expect(parseChatWsPayload("5")).toBeNull();
    expect(parseChatWsPayload("[]")).toBeNull();
    expect(parseChatWsPayload("null")).toBeNull();
  });
});
