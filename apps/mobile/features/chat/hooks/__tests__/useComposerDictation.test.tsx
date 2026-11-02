import type { SharedValue } from "react-native-reanimated";
import React, { useLayoutEffect } from "react";
import { Text } from "react-native";
import { act, render } from "@testing-library/react-native";

import { useComposerDictation } from "@/features/chat/hooks/useComposerDictation";
import type { User } from "@/lib/api";

// The composer mic as ChatScreen wires it: the take's thread, the plan gate
// and the route-change cancel.

type VoiceOptions = { onTranscript: (text: string) => void; onPlanRequired?: () => void };
let voiceOptions: VoiceOptions;
const mockToggle = jest.fn(async () => {});
const mockCancel = jest.fn();
let mockRecording = false;
jest.mock("@/features/speech/hooks/useVoiceInput", () => ({
  useVoiceInput: (options: VoiceOptions) => {
    voiceOptions = options;
    return {
      voiceInputAvailable: true,
      voiceRecording: mockRecording,
      voiceTranscribing: false,
      voiceMeterLevel: { value: 0.2 } as SharedValue<number>,
      toggleVoiceInput: mockToggle,
      cancelVoiceInput: mockCancel,
    };
  },
}));

let input = "";
const setInput = jest.fn((next: string | ((prev: string) => string)) => {
  input = typeof next === "function" ? next(input) : next;
});
const openUpgrade = jest.fn();
const openUpgradeRef = { current: openUpgrade };
const plusUser = { plan: "plus", features: ["speech_transcription"] } as unknown as User;
const freeUser = { plan: "free", features: [] } as unknown as User;
let current: ReturnType<typeof useComposerDictation>;

function Probe({ routeChatId, user = plusUser }: { routeChatId?: string; user?: User | null }) {
  const result = useComposerDictation({
    token: "token",
    user,
    routeChatId,
    setInput,
    openUpgradeRef,
    t: (key) => key,
  });
  useLayoutEffect(() => { current = result; });
  return <Text>mic</Text>;
}

beforeEach(() => {
  jest.clearAllMocks();
  input = "";
  mockRecording = false;
});

it("appends a transcript after the typed text, or fills an empty composer", async () => {
  await render(<Probe routeChatId="chat-1" />);
  await act(async () => { current.toggleVoiceInput(); });
  expect(mockToggle).toHaveBeenCalledTimes(1);
  voiceOptions.onTranscript("hello there");
  expect(input).toBe("hello there");
  input = "  draft  ";
  voiceOptions.onTranscript("more");
  expect(input).toBe("draft more");
});

it("drops a transcript once the composer has moved to another thread", async () => {
  const view = await render(<Probe routeChatId="chat-1" />);
  await act(async () => { current.toggleVoiceInput(); });
  await view.rerender(<Probe routeChatId="chat-2" />);
  voiceOptions.onTranscript("for chat one");
  expect(setInput).not.toHaveBeenCalled();
});

it("cancels the open take when the route changes", async () => {
  const view = await render(<Probe routeChatId="chat-1" />);
  const mountCancels = mockCancel.mock.calls.length;
  await view.rerender(<Probe routeChatId="chat-1" />);
  expect(mockCancel).toHaveBeenCalledTimes(mountCancels);
  await view.rerender(<Probe routeChatId="chat-2" />);
  expect(mockCancel).toHaveBeenCalledTimes(mountCancels + 1);
});

it("opens the plans instead of recording when the plan has no dictation", async () => {
  await render(<Probe routeChatId="chat-1" user={freeUser} />);
  await act(async () => { current.toggleVoiceInput(); });
  expect(openUpgrade).toHaveBeenCalledWith("voice");
  expect(mockToggle).not.toHaveBeenCalled();
});

it("still stops a take already running, whatever the plan", async () => {
  mockRecording = true;
  await render(<Probe routeChatId="chat-1" user={freeUser} />);
  await act(async () => { current.toggleVoiceInput(); });
  expect(mockToggle).toHaveBeenCalledTimes(1);
  expect(openUpgrade).not.toHaveBeenCalled();
});

it("opens the plans when the server refuses dictation", async () => {
  await render(<Probe routeChatId="chat-1" />);
  voiceOptions.onPlanRequired?.();
  expect(openUpgrade).toHaveBeenCalledWith("voice");
});
