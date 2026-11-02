import { fireEvent, render, waitFor } from "@testing-library/react-native";

import PreferencesSettingsScreen from "@/features/account/screens/PreferencesSettingsScreen";

const mockSetHaptics = jest.fn();
const mockUpdateUser = jest.fn();

jest.mock("expo-router", () => ({ Redirect: () => null, router: { push: jest.fn() } }));
jest.mock("@/contexts/AuthContext", () => ({
  useAuth: () => ({ token: "tok", user: { response_tone: "casual" }, updateUser: mockUpdateUser }),
}));
jest.mock("@/contexts/actionFeedbackCore", () => ({ useActionFeedbackOptional: () => null }));
jest.mock("@/contexts/AppearanceContext", () => ({
  useHaptics: () => ({ enabled: true, setEnabled: mockSetHaptics }),
}));
jest.mock("@/ui/overlay/FieldSheet", () => ({
  FieldSheet: () => null,
}));

beforeEach(() => jest.clearAllMocks());

it("turns haptics off on this device from Personalization", async () => {
  const { getByRole } = await render(<PreferencesSettingsScreen />);
  await fireEvent.press(getByRole("switch", { name: "settings.haptics" }));
  expect(mockSetHaptics).toHaveBeenCalledWith(false);
});

it("starts Emoji at a few and saves the level the user picks", async () => {
  mockUpdateUser.mockResolvedValue(undefined);
  const { getByText, getByLabelText, queryByTestId } = await render(
    <PreferencesSettingsScreen />,
  );
  expect(getByText("settings.emoji_some")).toBeTruthy();

  await fireEvent.press(getByText("settings.emoji"));
  expect(queryByTestId("select-menu")).toBeTruthy();
  expect(getByLabelText("settings.emoji_some").props.accessibilityState.checked).toBe(true);
  await fireEvent.press(getByLabelText("settings.emoji_more"));

  await waitFor(() => expect(mockUpdateUser).toHaveBeenCalledWith({ emoji_use: "more" }));
});
