import {
  LIVE_TALK_CONNECT_WARMUP_MS,
  LIVE_TALK_PLAYBACK_TAIL_MS,
  liveTalkCallErrorKey,
  liveTalkErrorGate,
  liveTalkGateMessageKey,
  liveTalkGate,
  liveTalkOrbA11yHintKey,
  liveTalkOrbA11yKey,
  liveTalkOrbAction,
  liveTalkPhaseA11yKey,
  liveTalkOrbMode,
  liveTalkShouldAttachSession,
  liveTalkShouldCloseOnChatChange,
  liveTalkShouldCloseOnAppState,
  liveTalkDataChannelText,
  liveTalkMuteA11yKey,
  liveTalkShowsSideChrome,
  liveTalkLocalMicEnabled,
  liveTalkShouldCreateResponse,
  isLikelyAssistantEcho,
  LIVE_TALK_MAX_SESSION_MS,
  liveTalkSaveEndsCall,
  liveTalkSaveFailedKey,
  liveTalkSessionLimitMs,
  type LiveTalkStatus,
} from "@/features/speech/model/liveTalkLogic";

const proReady: LiveTalkStatus = {
  enabled: true,
  entitled: true,
  remaining: 12,
  limit: 30,
};

describe("liveTalkGate", () => {
  it("blocks offline before status", () => {
    expect(liveTalkGate(proReady, true)).toBe("offline");
  });

  it("opens upgrade when free (limit 0)", () => {
    expect(
      liveTalkGate({ enabled: true, entitled: false, remaining: 0, limit: 0 }, false),
    ).toBe("upgrade");
  });

  it("opens limit when Pro is exhausted", () => {
    expect(
      liveTalkGate({ enabled: true, entitled: true, remaining: 0, limit: 30 }, false),
    ).toBe("limit");
  });

  // It said "isn't available in this version of the app. Update the app": the server's
  // switch is no old app.
  it("says live talk is off when the server has it switched off", () => {
    expect(liveTalkGate({ ...proReady, enabled: false, entitled: false }, false)).toBe("off");
  });

  it("allows a remaining Pro turn", () => {
    expect(liveTalkGate(proReady, false)).toBe("ok");
  });

  it("says the month's minutes are used when less than a session is left", () => {
    const status: LiveTalkStatus = {
      enabled: true,
      entitled: true,
      remaining: 0,
      limit: 60,
      remaining_seconds: 30,
      limit_seconds: 3600,
      min_session_seconds: 60,
    };
    expect(liveTalkGate(status, false)).toBe("limit");
    expect(liveTalkGate({ ...status, remaining: 1, remaining_seconds: 90 }, false)).toBe("ok");
  });
});

describe("liveTalkSessionLimitMs", () => {
  it("hangs up when the server's reservation runs out", () => {
    expect(liveTalkSessionLimitMs(120)).toBe(120_000);
  });

  it("never runs past the longest session, and falls back to it", () => {
    expect(liveTalkSessionLimitMs(99_999)).toBe(LIVE_TALK_MAX_SESSION_MS);
    expect(liveTalkSessionLimitMs(undefined)).toBe(LIVE_TALK_MAX_SESSION_MS);
    expect(liveTalkSessionLimitMs(0)).toBe(LIVE_TALK_MAX_SESSION_MS);
  });
});

describe("liveTalkShouldAttachSession", () => {
  it("drops the session when close or a newer open bumped the generation", () => {
    expect(liveTalkShouldAttachSession(3, 3)).toBe(true);
    expect(liveTalkShouldAttachSession(3, 4)).toBe(false);
  });
});

describe("liveTalkShouldCloseOnChatChange", () => {
  it("closes only when the bound chat is left", () => {
    expect(liveTalkShouldCloseOnChatChange("chat-a", "chat-b")).toBe(true);
    expect(liveTalkShouldCloseOnChatChange("chat-a", "chat-a")).toBe(false);
    expect(liveTalkShouldCloseOnChatChange("chat-a", null)).toBe(true);
    expect(liveTalkShouldCloseOnChatChange(null, "chat-b")).toBe(false);
  });
});

describe("liveTalkShouldCloseOnAppState", () => {
  it("closes when the app goes to the background", () => {
    expect(liveTalkShouldCloseOnAppState("background")).toBe(true);
    expect(liveTalkShouldCloseOnAppState("active")).toBe(false);
  });

  it("stays on through iOS's inactive moments, its microphone prompt among them", () => {
    expect(liveTalkShouldCloseOnAppState("inactive")).toBe(false);
  });
});

describe("liveTalkDataChannelText", () => {
  it("reads string payloads and UTF-8 bytes", () => {
    expect(liveTalkDataChannelText('{"type":"response.done"}')).toBe('{"type":"response.done"}');
    expect(liveTalkDataChannelText(new TextEncoder().encode('{"type":"x"}'))).toBe('{"type":"x"}');
    expect(liveTalkDataChannelText(null)).toBeNull();
  });
});

describe("liveTalkErrorGate", () => {
  // Every 403 opened the paywall: consent_required too, on top of the consent step.
  it.each([
    [{ status: 403, code: "not_in_plan" }, "upgrade"],
    [{ status: 403, code: "consent_required" }, "consent"],
    [{ status: 403, code: "forbidden" }, "connect_failed"],
    [{ status: 403 }, "connect_failed"],
  ])("keys a 403 on its code: %j", (error, gate) => {
    expect(liveTalkErrorGate(error)).toBe(gate);
  });

  // Every 429 said "You've used this month's live talk minutes": a rate limit, the
  // spend cap and a call's last save too. Only `live_talk_minutes_used` means that.
  it.each([
    [{ status: 429, code: "live_talk_minutes_used" }, "limit"],
    [{ status: 429, code: "speech_rate_limited" }, "rate_limited"],
    [{ status: 429, code: "rate_limited" }, "rate_limited"],
    // The API's own request limit names no code.
    [{ status: 429, code: null }, "rate_limited"],
    [{ status: 429 }, "rate_limited"],
    [{ status: 429, code: "voice_spend_cap" }, "paused"],
    [{ status: 429, code: "live_talk_saves_used" }, "saves_used"],
  ])("keys a 429 on its code: %j", (error, gate) => {
    expect(liveTalkErrorGate(error)).toBe(gate);
  });

  // "Update the app" is only for a build without WebRTC; a provider that failed, or a
  // connection that never came up, is worth another try.
  it.each([
    [{ status: 502, code: "upstream_failed" }],
    [new Error("Realtime voice connection timed out")],
    [new Error("OpenAI Realtime returned an invalid SDP answer")],
    [new TypeError("Network request failed")],
    [Object.assign(new Error("Request canceled"), { name: "AbortError" })],
  ])("says a failed connection %j is worth another try", (error) => {
    expect(liveTalkErrorGate(error)).toBe("connect_failed");
  });

  it("says a server with live talk switched off is off, not an old app", () => {
    expect(liveTalkErrorGate({ status: 404, code: "not_available" })).toBe("off");
  });

  it("maps a missing WebRTC native module to unavailable", () => {
    expect(liveTalkErrorGate(new Error("webrtc_unavailable"))).toBe("unavailable");
  });

  // A microphone that gave no audio said "update the app".
  it("maps a microphone with no audio to its own gate and line", () => {
    expect(liveTalkErrorGate(new Error("microphone_unavailable"))).toBe("mic_unavailable");
    expect(liveTalkGateMessageKey("mic_unavailable")).toBe("chat.live_talk_mic_unavailable");
  });

  it("maps a missing Realtime server key to unconfigured only when the server says so", () => {
    expect(liveTalkErrorGate({ status: 503, code: "not_configured" })).toBe("unconfigured");
  });

  // Every 503 said "Live talk isn't set up on this server yet", a Redis outage included.
  it.each([
    [{ status: 503, code: "unavailable" }],
    [{ status: 503, code: null }],
    [{ status: 502, code: null }],
    [{ status: 504, code: null }],
  ])("maps an outage %j to outage", (error) => {
    expect(liveTalkErrorGate(error)).toBe("outage");
  });

  it.each([
    ["outage", "common.service_unavailable"],
    ["unconfigured", "chat.live_talk_not_configured"],
    ["limit", "chat.live_talk_limit_body"],
    ["rate_limited", "chat.live_talk_rate_limited"],
    ["paused", "chat.live_talk_paused"],
    ["saves_used", "chat.live_talk_saves_used"],
    ["connect_failed", "chat.live_talk_connect_failed"],
    ["off", "chat.live_talk_off"],
    ["offline", "chat.offline_body"],
    ["unavailable", "chat.live_talk_unavailable_body"],
  ] as const)("words the %s gate", (gate, key) => {
    expect(liveTalkGateMessageKey(gate)).toBe(key);
  });

  // A save the plan or the session no longer allowed left the call open: the provider ran
  // on until the reserved minutes did, and nothing more saved.
  it("ends the call on a refused save's 429, or one the plan, session or server no longer allows", () => {
    const gates = ["limit", "rate_limited", "paused", "saves_used", "upgrade", "consent", "session_ended", "off",
      "outage", "unavailable", "connect_failed", "unconfigured"] as const;
    expect(gates.filter(liveTalkSaveEndsCall)).toEqual(
      ["limit", "rate_limited", "paused", "saves_used", "upgrade", "consent", "session_ended", "off"],
    );
  });

  it("keys a save that names no live session on its code", () => {
    expect(liveTalkErrorGate({ status: 403, code: "live_talk_session_ended" })).toBe("session_ended");
    expect(liveTalkGateMessageKey("session_ended")).toBe("chat.live_talk_session_ended");
  });

  // Both showed the provider's English ("Realtime voice data channel failed").
  it("words an error during a call: a lost connection, or this reply", () => {
    expect(liveTalkCallErrorKey(true)).toBe("chat.live_talk_connect_failed");
    expect(liveTalkCallErrorKey(false)).toBe("chat.error_generic");
    expect(liveTalkCallErrorKey(undefined)).toBe("chat.error_generic");
  });

  // Any other refused save showed the server's English ("Chat not found").
  it.each([
    ["connect_failed", "chat.live_talk_save_failed"],
    ["outage", "common.service_unavailable"],
  ] as const)("words a refused save that keeps the call: %s", (gate, key) => {
    expect(liveTalkSaveFailedKey(gate)).toBe(key);
  });

  // F8.8: a denied microphone said "Live talk needs a dev build", which is false
  // and leaves the user nothing to do. Only Settings can turn the mic back on.
  it.each([
    [{ name: "SecurityError", message: "Permission denied." }],
    [{ name: "NotAllowedError", message: "The request is not allowed" }],
    [new Error("Permission denied")],
  ])("maps a denied microphone %j to the mic-permission gate", (error) => {
    expect(liveTalkErrorGate(error)).toBe("mic_permission");
  });

  it("never reads an API refusal as a microphone denial", () => {
    expect(
      liveTalkErrorGate({ status: 403, code: "not_in_plan", message: "Live talk is not allowed on your plan" }),
    ).toBe("upgrade");
  });
});

describe("Live Talk screen-reader labels (S7.13)", () => {
  it("gives listening, thinking and speaking distinct labels, and idle the feature name", () => {
    const keys = (["recording", "thinking", "speaking"] as const).map(liveTalkOrbA11yKey);
    expect(new Set(keys).size).toBe(3);
    expect(liveTalkOrbA11yKey("idle")).toBe("chat.live_talk_a11y");
    expect(liveTalkOrbA11yKey("recording")).toBe("chat.live_talk_listening_a11y");
    expect(liveTalkOrbA11yKey("speaking")).toBe("chat.live_talk_speaking_a11y");
  });

  it("announces every phase but idle, and offers cancel only while thinking", () => {
    expect(liveTalkPhaseA11yKey("idle")).toBeNull();
    expect(liveTalkPhaseA11yKey("thinking")).toBe("chat.live_talk_thinking_a11y");
    expect(liveTalkOrbA11yHintKey("thinking")).toBe("chat.live_talk_cancel_a11y");
    expect(liveTalkOrbA11yHintKey("speaking")).toBeNull();
  });
});

describe("liveTalkOrbMode", () => {
  it("maps listen vs speak without using on-screen copy", () => {
    expect(liveTalkOrbMode("recording")).toBe("listen");
    expect(liveTalkOrbMode("speaking")).toBe("speak");
    expect(liveTalkOrbMode("thinking")).toBe("think");
    expect(liveTalkOrbMode("idle")).toBe("idle");
  });
});

describe("liveTalkOrbAction", () => {
  it("does not mute from the orb; mic control owns mute", () => {
    expect(liveTalkOrbAction("speaking")).toBe("none");
    expect(liveTalkOrbAction("thinking")).toBe("cancelThink");
    expect(liveTalkOrbAction("recording")).toBe("finishListen");
    expect(liveTalkOrbAction("idle")).toBe("begin");
    expect(liveTalkMuteA11yKey(false)).toBe("chat.live_talk_mute_a11y");
    expect(liveTalkMuteA11yKey(true)).toBe("chat.live_talk_unmute_a11y");
    expect(liveTalkShowsSideChrome("")).toBe(true);
    expect(liveTalkShowsSideChrome("  ")).toBe(true);
    expect(liveTalkShowsSideChrome("hello")).toBe(false);
  });
});

describe("liveTalkLocalMicEnabled", () => {
  it("closes capture while the assistant is playing even if the user is not muted", () => {
    expect(liveTalkLocalMicEnabled(false, false)).toBe(true);
    expect(liveTalkLocalMicEnabled(false, true)).toBe(false);
    expect(liveTalkLocalMicEnabled(true, false)).toBe(false);
  });
});

describe("liveTalkShouldCreateResponse", () => {
  it("uses a connect warmup and a short playback tail before the mic reopens", () => {
    expect(LIVE_TALK_CONNECT_WARMUP_MS).toBe(1_500);
    expect(LIVE_TALK_PLAYBACK_TAIL_MS).toBe(500);
  });

  it("does not create a model turn from connect noise or assistant echo", () => {
    expect(
      liveTalkShouldCreateResponse({
        sessionReadyForTurns: false,
        assistantSpeaking: false,
        userMuted: false,
        acceptedUserUtterance: true,
      }),
    ).toBe(false);
    expect(
      liveTalkShouldCreateResponse({
        sessionReadyForTurns: true,
        assistantSpeaking: true,
        userMuted: false,
        acceptedUserUtterance: true,
      }),
    ).toBe(false);
    expect(
      liveTalkShouldCreateResponse({
        sessionReadyForTurns: true,
        assistantSpeaking: false,
        userMuted: false,
        acceptedUserUtterance: false,
      }),
    ).toBe(false);
    expect(
      liveTalkShouldCreateResponse({
        sessionReadyForTurns: true,
        assistantSpeaking: false,
        userMuted: false,
        acceptedUserUtterance: true,
      }),
    ).toBe(true);
  });
});

describe("isLikelyAssistantEcho", () => {
  it("drops speaker-bleed fragments of the last assistant line", () => {
    expect(
      isLikelyAssistantEcho("Nice", "Nice to hear from you. What's on your mind today?"),
    ).toBe(true);
    expect(isLikelyAssistantEcho("what's the weather", "Nice to hear from you")).toBe(false);
  });
});
