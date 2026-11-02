import {
  initialRealtimeTurnState,
  reduceRealtimeTurn,
  type RealtimeTurnCommand,
  type RealtimeTurnEvent,
  type RealtimeTurnState,
} from "@/features/speech/model/realtimeTurnState";

// realtimeTools (the function-call parser) sits beside the lookup client.
jest.mock("@/features/speech/api", () => ({ speechApi: {} }));

const server = (event: Record<string, unknown>): RealtimeTurnEvent => ({ type: "server_event", event, receivedAt: 7 });

/** Applies events in order; returns the last state and every command except logs. */
function run(state: RealtimeTurnState, ...events: RealtimeTurnEvent[]) {
  const commands: RealtimeTurnCommand[] = [];
  for (const event of events) {
    const step = reduceRealtimeTurn(state, event);
    state = step.state;
    commands.push(...step.commands.filter((command) => command.type !== "log"));
  }
  return { state, commands };
}

/** Ready for turns, the user said u1 and the assistant is answering it as a1. */
function replying(bargeIn: boolean): RealtimeTurnState {
  return run(
    initialRealtimeTurnState(bargeIn),
    { type: "session_ready", reason: "test" },
    server({ type: "input_audio_buffer.speech_started", item_id: "u1" }),
    server({ type: "input_audio_buffer.speech_stopped" }),
    server({ type: "response.created", response: { id: "a1" } }),
    server({ type: "response.output_audio_transcript.delta", response_id: "a1", delta: "The capital" }),
  ).state;
}

describe("reduceRealtimeTurn: barge-in", () => {
  it("interrupts the reply when the user talks over it and starts a new turn", () => {
    const before = replying(true);
    const { state, commands } = run(before, server({ type: "input_audio_buffer.speech_started", item_id: "u2" }));
    expect(commands).toEqual([
      { type: "emit", event: { type: "response_interrupted" } },
      { type: "clear_timer", timer: "mic_resume" },
      { type: "emit", event: { type: "speech_started", turnId: "u2" } },
    ]);
    expect(state).toMatchObject({ assistantSpeaking: false, activeResponseId: null, assistantTranscript: "" });
    expect(state.turnEpoch).toBe(before.turnEpoch + 1);
  });

  it("keeps the mic open for the reply and drops the interrupted reply's late events", () => {
    const opened = run(replying(true), server({ type: "response.created", response: { id: "a2" } }));
    expect(opened.commands).toContainEqual({ type: "set_mic", enabled: true });
    const late = run(
      replying(true),
      server({ type: "input_audio_buffer.speech_started", item_id: "u2" }),
      server({ type: "response.output_audio_transcript.delta", response_id: "a1", delta: "stale" }),
      server({ type: "response.done", response: { id: "a1", output: [] } }),
    );
    expect(late.commands.filter((command) => command.type === "emit")).toHaveLength(2);
  });

  it("cancels a reply created while the user is still speaking", () => {
    const speaking = run(replying(true), server({ type: "input_audio_buffer.speech_started", item_id: "u2" })).state;
    const { state, commands } = run(speaking, server({ type: "response.created", response: { id: "a2" } }));
    expect(commands).toEqual([{ type: "send", payload: { type: "response.cancel", response_id: "a2" } }]);
    expect(state.activeResponseId).toBeNull();
  });

  it("finishes the reply when playback stops, or 12 s after response.done without a stop", () => {
    const done = run(replying(true), server({ type: "response.done", response: { id: "a1", output: [] } }));
    expect(done.commands).toEqual([
      { type: "start_timer", timer: "mic_resume", ms: 12_000, then: { type: "playback_fallback" } },
    ]);
    expect(run(done.state, { type: "playback_fallback" }).commands).toEqual([
      { type: "emit", event: { type: "response_done" } },
    ]);
    expect(run(done.state, server({ type: "output_audio_buffer.stopped", response_id: "a1" })).commands).toEqual([
      { type: "clear_timer", timer: "mic_resume" },
      { type: "emit", event: { type: "response_done" } },
    ]);
  });
});

describe("reduceRealtimeTurn: echo drop (half duplex)", () => {
  it("closes the mic for the reply and reopens it 500 ms after playback", () => {
    const created = run(
      run(initialRealtimeTurnState(false), { type: "session_ready", reason: "test" }).state,
      server({ type: "input_audio_buffer.speech_started", item_id: "u1" }),
      server({ type: "input_audio_buffer.speech_stopped" }),
    );
    expect(created.commands).toContainEqual({ type: "set_mic", enabled: false });
    const stopped = run(replying(false), server({ type: "output_audio_buffer.stopped", response_id: "a1" }));
    expect(stopped.commands).toEqual([
      { type: "start_timer", timer: "mic_resume", ms: 500, then: { type: "resume_mic" } },
    ]);
    expect(run(stopped.state, { type: "resume_mic" }).commands).toEqual([{ type: "set_mic", enabled: true }]);
  });

  it("clears speech heard during the reply and cancels a reply the server starts for it", () => {
    const { state, commands } = run(
      replying(false),
      server({ type: "input_audio_buffer.speech_started", item_id: "echo" }),
      server({ type: "response.created", response: { id: "a2" } }),
    );
    expect(commands).toEqual([
      { type: "send", payload: { type: "input_audio_buffer.clear" } },
      { type: "send", payload: { type: "input_audio_buffer.clear" } },
      { type: "send", payload: { type: "response.cancel" } },
    ]);
    expect(state).toMatchObject({ suppressCurrentInputTurn: true, acceptedUserUtterance: false, activeInputId: "u1" });
  });

  it("drops a transcript that repeats the assistant's last line", () => {
    const { commands } = run(
      replying(false),
      server({ type: "response.output_audio_transcript.done", response_id: "a1", transcript: "The capital is Paris." }),
      server({ type: "conversation.item.input_audio_transcription.completed", item_id: "u1", transcript: "is Paris" }),
    );
    expect(commands.at(-1)).toEqual({ type: "send", payload: { type: "input_audio_buffer.clear" } });
    expect(commands).not.toContainEqual(expect.objectContaining({ event: expect.objectContaining({ type: "user_transcript" }) }));
  });
});

describe("reduceRealtimeTurn: turn rules", () => {
  it("answers a lookup from an older turn as cancelled and asks for no reply", () => {
    const call = { type: "function_call", name: "web_search", call_id: "t1", arguments: '{"query":"q"}' };
    const asked = run(replying(true), server({ type: "response.done", response: { id: "a1", output: [call] } }));
    expect(asked.commands).toEqual([
      { type: "run_tools", epoch: 1, turnId: "u1", calls: [{ call, withinLimit: true }] },
    ]);
    const { commands } = run(
      asked.state,
      { type: "cancel_response" },
      { type: "tool_output", epoch: 1, callId: "t1", result: { content: "Old", sources: [{ title: "S", url: "https://s" }] } },
      { type: "tools_settled", epoch: 1 },
    );
    expect(commands.filter((command) => command.type === "send").map((command) => command.payload)).toEqual([
      { type: "response.cancel" },
      { type: "output_audio_buffer.clear" },
      {
        type: "conversation.item.create",
        item: { type: "function_call_output", call_id: "t1", output: '{"content":"Lookup cancelled by a new user turn."}' },
      },
    ]);
  });

  it("does nothing with messages once closed", () => {
    const closed = run(replying(true), { type: "close" }).state;
    expect(reduceRealtimeTurn(closed, server({ type: "error", error: { message: "x" } })).commands).toEqual([]);
  });

  it("never changes the state it is given", () => {
    const state = Object.freeze(replying(false));
    expect(() => run(state, server({ type: "input_audio_buffer.speech_started", item_id: "u2" }), { type: "set_muted", muted: true })).not.toThrow();
    expect(state.userMuted).toBe(false);
  });
});

describe("reduceRealtimeTurn: a failed connection", () => {
  it.each(["peer_failed", "channel_failed"] as const)("%s is a fatal error, so the session closes", (type) => {
    const { commands } = run(replying(true), { type, message: "network lost" });
    expect(commands).toContainEqual({ type: "emit", event: { type: "error", message: "network lost", fatal: true } });
  });

  it("a server error event is not fatal: the session goes on", () => {
    const { commands } = run(replying(true), server({ type: "error", error: { message: "rate limited" } }));
    expect(commands).toContainEqual({ type: "emit", event: { type: "error", message: "rate limited" } });
  });
});
