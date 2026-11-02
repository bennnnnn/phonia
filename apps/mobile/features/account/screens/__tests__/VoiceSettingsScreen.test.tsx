import { act, fireEvent, render, waitFor } from "@testing-library/react-native";

import VoiceSettingsScreen from "@/features/account/screens/VoiceSettingsScreen";

const mockUpdateUser = jest.fn();
const mockSetSpeechRate = jest.fn();
const mockSetTtsModel = jest.fn();
let mockVoice: string | null = null;

jest.mock("expo-router", () => ({ Redirect: () => null, router: { push: jest.fn() } }));
jest.mock("@/contexts/AuthContext", () => ({
  useAuth: () => ({ token: "tok", user: { tts_voice: mockVoice }, updateUser: mockUpdateUser }),
}));
jest.mock("@/contexts/actionFeedbackCore", () => ({ useActionFeedbackOptional: () => null }));
jest.mock("@/features/speech/model/speechRate", () => ({
  SPEECH_RATES: [0.75, 1, 1.25, 1.5],
  getSpeechRate: jest.fn(async () => 1.25),
  setSpeechRate: (...args: unknown[]) => mockSetSpeechRate(...args),
}));
jest.mock("@/features/speech/model/ttsPreference", () => ({
  TTS_DEVICE_MODEL: "device",
  TTS_QUALITY_MODEL: "speech-tts-model",
  getTtsModel: jest.fn(async () => "speech-tts-model"),
  setTtsModel: (...args: unknown[]) => mockSetTtsModel(...args),
}));

beforeEach(() => {
  jest.clearAllMocks();
  mockVoice = null;
  mockUpdateUser.mockResolvedValue(undefined);
});

it("shows the default voice and this phone's saved speed", async () => {
  const view = await render(<VoiceSettingsScreen />);
  expect(view.getByLabelText("settings.voice, settings.voice_default")).toBeTruthy();
  expect(await view.findByLabelText("settings.voice_speed, 1.25×")).toBeTruthy();
});

it("saves a chosen voice on the account", async () => {
  const view = await render(<VoiceSettingsScreen />);
  await fireEvent.press(view.getByText("settings.voice"));
  await fireEvent.press(view.getByLabelText("Cedar"));
  await waitFor(() => expect(mockUpdateUser).toHaveBeenCalledWith({ tts_voice: "cedar" }));
});

it("puts the server default back with Default", async () => {
  mockVoice = "sage";
  const view = await render(<VoiceSettingsScreen />);
  expect(view.getByLabelText("settings.voice, Sage")).toBeTruthy();
  await fireEvent.press(view.getByText("settings.voice"));
  await fireEvent.press(view.getByLabelText("settings.voice_default"));
  await waitFor(() => expect(mockUpdateUser).toHaveBeenCalledWith({ tts_voice: null }));
});

it("keeps speed and the on-device voice on this phone", async () => {
  const view = await render(<VoiceSettingsScreen />);
  await view.findByLabelText("settings.voice_speed, 1.25×");
  await fireEvent.press(view.getByText("settings.voice_speed"));
  await fireEvent.press(view.getByLabelText("1.5×"));
  expect(mockSetSpeechRate).toHaveBeenCalledWith(1.5);

  await act(async () => {
    fireEvent.press(view.getByRole("switch", { name: "settings.voice_on_device" }));
  });
  expect(mockSetTtsModel).toHaveBeenCalledWith("device");
  expect(mockUpdateUser).not.toHaveBeenCalled();
});
