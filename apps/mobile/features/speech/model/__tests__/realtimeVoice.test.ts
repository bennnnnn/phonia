jest.mock("react-native", () => ({
  Platform: { OS: "ios" },
}));
jest.mock("expo-modules-core", () => ({
  requireOptionalNativeModule: () => ({ isDevice: false }),
}));
jest.mock("expo-constants", () => ({}));

jest.mock("@/lib/speech/voiceAudio", () => ({
  yieldMicToWebRtc: jest.fn(async () => undefined),
}));

jest.mock("react-native-webrtc", () => ({
  __WEBRTC_STUB__: true,
}));

jest.mock("@/features/speech/api", () => ({
  speechApi: { createRealtimeSession: jest.fn() },
}));

import { createRealtimeVoiceSession, isRealtimeVoiceAvailable, webRtcMicConstraints } from "@/features/speech/model/realtimeVoice";

describe("realtimeVoice", () => {
  it("is unavailable when WebRTC is not in this native binary", () => {
    expect(isRealtimeVoiceAvailable()).toBe(false);
  });

  it("does not crash chat when opening Live Talk without WebRTC", async () => {
    await expect(
      createRealtimeVoiceSession({
        token: "tok",
        onEvent: () => undefined,
      }),
    ).rejects.toThrow("webrtc_unavailable");
  });

  it("disables iOS VoiceProcessing so Simulator CoreAudio does not deadlock", () => {
    expect(webRtcMicConstraints()).toEqual({
      echoCancellation: false,
      noiseSuppression: false,
      autoGainControl: false,
    });
  });
});
