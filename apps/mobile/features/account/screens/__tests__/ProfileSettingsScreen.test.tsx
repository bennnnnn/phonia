import type { ReactNode } from "react";
import { Alert } from "react-native";
import { fireEvent, render, waitFor } from "@testing-library/react-native";

import ProfileSettingsScreen from "@/features/account/screens/ProfileSettingsScreen";

const mockUpdateUser = jest.fn();
const mockPickProfilePhoto = jest.fn();
const mockUploadPhoto = jest.fn();
let mockUser: Record<string, unknown>;

jest.mock("expo-router", () => ({ Redirect: () => null, router: { push: jest.fn() } }));
jest.mock("@/contexts/AuthContext", () => ({
  useAuth: () => ({ token: "tok", user: mockUser, updateUser: mockUpdateUser }),
}));
jest.mock("@/contexts/actionFeedbackCore", () => ({ useActionFeedbackOptional: () => null }));
jest.mock("@/lib/config", () => ({ getApiUrl: () => "https://api.recall.test" }));
jest.mock("@/lib/auth", () => ({ getSessionGeneration: () => 0 }));
jest.mock("@/lib/api", () => ({ api: { cancelAttachment: jest.fn() } }));
jest.mock("@/features/account/model/profilePhoto", () => ({
  pickProfilePhoto: (...args: unknown[]) => mockPickProfilePhoto(...args),
  discardProfilePhoto: jest.fn(),
}));
jest.mock("@/features/attachments/model/attachments", () => ({
  uploadChatAttachment: (...args: unknown[]) => mockUploadPhoto(...args),
  PhotoLibraryPermissionError: class extends Error {},
  NativePickerBusyError: class extends Error {},
  NativePickerTimeoutError: class extends Error {},
}));
jest.mock("@/ui/overlay/Sheet", () => {
  const { View: RNView } = jest.requireActual("react-native") as typeof import("react-native");
  return {
    Sheet: ({ children, visible }: { children: ReactNode; visible: boolean }) =>
      visible ? <RNView>{children}</RNView> : null,
  };
});

beforeEach(() => {
  jest.clearAllMocks();
  mockUser = {
    id: "22222222-2222-4222-8222-222222222222",
    name: "bini",
    email: "dev@recall.local",
    age: 54,
    country: "Ethiopia",
    job: null,
    location: null,
    location_enabled: false,
  };
  mockUpdateUser.mockResolvedValue(undefined);
  mockPickProfilePhoto.mockResolvedValue(null);
  mockUploadPhoto.mockResolvedValue("11111111-1111-4111-8111-111111111111");
  jest.spyOn(Alert, "alert").mockImplementation(() => {});
});

it("shows the name and the facts about you; location lives under Privacy", async () => {
  const { getByText, queryByText } = await render(<ProfileSettingsScreen />);
  expect(getByText("bini")).toBeTruthy();
  expect(getByText("settings.about_you")).toBeTruthy();
  expect(getByText("54")).toBeTruthy();
  expect(getByText("Ethiopia")).toBeTruthy();
  expect(getByText("settings.not_set")).toBeTruthy();
  expect(queryByText("settings.use_current_location")).toBeNull();
});

it("opens the profile editor from the avatar and saves the name", async () => {
  const { getByDisplayValue, getByLabelText, queryByTestId, queryByText } =
    await render(<ProfileSettingsScreen />);

  expect(queryByTestId("settings-profile-sheet")).toBeNull();
  await fireEvent.press(getByLabelText("settings.edit_profile"));
  expect(queryByTestId("settings-profile-sheet")).toBeTruthy();
  expect(queryByText("settings.username")).toBeNull();
  await fireEvent.changeText(getByDisplayValue("bini"), "  Bini  ");
  await fireEvent.press(getByLabelText("settings.save_profile"));

  await waitFor(() => expect(mockUpdateUser).toHaveBeenCalledWith({ name: "Bini" }));
  expect(queryByTestId("settings-profile-sheet")).toBeNull();
});

it("previews a chosen photo and uploads it only when Save profile is pressed", async () => {
  const photo = { localUri: "file:///profile-preview.jpg", contentType: "image/jpeg", fileName: "profile.jpg", kind: "image" };
  mockPickProfilePhoto.mockResolvedValue(photo);
  const { getByLabelText, getByTestId } = await render(<ProfileSettingsScreen />);

  await fireEvent.press(getByLabelText("settings.edit_profile"));
  await fireEvent.press(getByLabelText("settings.change_photo"));
  await waitFor(() => expect(getByTestId("avatar-image", { includeHiddenElements: true }).props.source.uri).toBe(photo.localUri));
  expect(mockUploadPhoto).not.toHaveBeenCalled();
  await fireEvent.press(getByLabelText("settings.save_profile"));
  await waitFor(() => expect(mockUpdateUser).toHaveBeenCalledWith({
    name: "bini",
    avatar_url: "/attachments/11111111-1111-4111-8111-111111111111/file",
  }));
});

it("cancels a profile draft without updating the account", async () => {
  const { getByLabelText, getByDisplayValue, getByText, queryByTestId } =
    await render(<ProfileSettingsScreen />);
  await fireEvent.press(getByLabelText("settings.edit_profile"));
  await fireEvent.changeText(getByDisplayValue("bini"), "Another name");
  await fireEvent.press(getByText("settings.cancel"));
  expect(queryByTestId("settings-profile-sheet")).toBeNull();
  expect(mockUpdateUser).not.toHaveBeenCalled();
});

it("saves a job and clears an age", async () => {
  const view = await render(<ProfileSettingsScreen />);
  await fireEvent.press(view.getByText("settings.job_label"));
  await fireEvent.changeText(view.getByPlaceholderText("settings.job_placeholder"), " Designer ");
  await fireEvent.press(view.getByLabelText("settings.save"));
  await waitFor(() => expect(mockUpdateUser).toHaveBeenCalledWith({ job: "Designer" }));

  await fireEvent.press(view.getByText("settings.age_label"));
  await fireEvent.changeText(view.getByPlaceholderText("settings.age_placeholder"), "");
  await fireEvent.press(view.getByLabelText("settings.save"));
  await waitFor(() => expect(mockUpdateUser).toHaveBeenCalledWith({ age: null }));
});

it("refuses an age outside 13 to 120 without saving", async () => {
  const view = await render(<ProfileSettingsScreen />);
  await fireEvent.press(view.getByText("settings.age_label"));
  await fireEvent.changeText(view.getByPlaceholderText("settings.age_placeholder"), "9");
  await fireEvent.press(view.getByLabelText("settings.save"));
  expect(Alert.alert).toHaveBeenCalledWith("common.error", "settings.age_invalid");
  expect(mockUpdateUser).not.toHaveBeenCalled();
});
