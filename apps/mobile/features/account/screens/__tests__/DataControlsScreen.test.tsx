import { Alert } from "react-native";
import { fireEvent, render, waitFor } from "@testing-library/react-native";

import DataControlsScreen from "@/features/account/screens/DataControlsScreen";
import fixture from "../../../../../../docs/fixtures/error_codes.json";
import { SharingUnavailableError } from "@/lib/shareUnavailable";

const mockUpdateUser = jest.fn();
const mockLocationLabel = jest.fn();
const mockConfirm = jest.fn();
const mockExport = jest.fn();
const mockCancelExport = jest.fn();
const mockDeleteAccount = jest.fn();
const mockDeleteAllChats = jest.fn();
const mockReplace = jest.fn();
const mockReportError = jest.fn();
const mockMergeUser = jest.fn();
const mockWithdraw = jest.fn();
const mockWriteCachedUser = jest.fn();
let mockProgress = "idle";
let mockUser: Record<string, unknown>;

jest.mock("expo-router", () => ({
  Redirect: () => null,
  router: { push: jest.fn() },
  useRouter: () => ({ replace: mockReplace }),
  useNavigation: () => ({ setOptions: jest.fn() }),
}));
jest.mock("@/contexts/AuthContext", () => ({
  useAuth: () => ({
    token: "tok",
    user: mockUser,
    updateUser: mockUpdateUser,
    mergeUser: mockMergeUser,
  }),
}));
jest.mock("@/contexts/actionFeedbackCore", () => ({ useActionFeedbackOptional: () => null }));
jest.mock("@/features/account/hooks/useDataControls", () => ({
  useDataControls: () => ({
    progress: mockProgress,
    exportData: mockExport,
    cancelExport: mockCancelExport,
    deleteAccount: mockDeleteAccount,
  }),
}));
jest.mock("@/lib/api", () => ({
  api: { archiveAllChats: jest.fn(), deleteAllChats: (...args: unknown[]) => mockDeleteAllChats(...args) },
  withdrawAiDataSharing: (...args: unknown[]) => mockWithdraw(...args),
}));
jest.mock("@/lib/cachedUser", () => ({
  writeCachedUser: (...args: unknown[]) => mockWriteCachedUser(...args),
}));
jest.mock("@/ui/overlay/dialogs", () => ({
  confirmDialog: (...args: unknown[]) => mockConfirm(...args),
  alertDialog: jest.fn(),
}));
jest.mock("@/features/chat/model/chatListCache", () => ({ invalidateChatListCache: jest.fn() }));
jest.mock("@/lib/reportRecoverableError", () => ({
  reportRecoverableError: (...args: unknown[]) => mockReportError(...args),
}));
jest.mock("@/lib/deviceLocation", () => ({
  getDeviceLocationLabel: (...args: unknown[]) => mockLocationLabel(...args),
}));
jest.mock("@/lib/expoRuntime", () => ({ canUseDeviceLocation: () => true }));
jest.mock("@/ui/controls/StackBackButton", () => ({
  StackBackButton: () => null,
  plainHeaderItems: () => [],
}));

beforeEach(() => {
  jest.clearAllMocks();
  mockUser = { name: "bini", location: null, location_enabled: false };
  mockUpdateUser.mockResolvedValue(undefined);
  mockConfirm.mockResolvedValue(true);
  mockExport.mockResolvedValue(true);
  mockDeleteAllChats.mockResolvedValue(undefined);
  mockProgress = "idle";
  jest.spyOn(Alert, "alert").mockImplementation(() => {});
});

it("opens with web search (on by default) and location, no explanation lines", async () => {
  const view = await render(<DataControlsScreen />);
  const search = view.getByRole("switch", { name: "settings.web_search" });
  expect(search.props.accessibilityState.checked).toBe(true);
  expect(view.getByText("settings.use_current_location")).toBeTruthy();
  expect(view.queryByText("settings.web_search_summary")).toBeNull();
  expect(view.queryByText("settings.location_summary")).toBeNull();
  // The policy itself lives once, under About.
  expect(view.queryByText("privacy.title")).toBeNull();
});

it("turns web search off for the account", async () => {
  const view = await render(<DataControlsScreen />);
  await fireEvent.press(view.getByRole("switch", { name: "settings.web_search" }));
  await waitFor(() => expect(mockUpdateUser).toHaveBeenCalledWith({ web_search_enabled: false }));
});

it("turns location on with the device's place", async () => {
  mockLocationLabel.mockResolvedValue("Addis Ababa, Ethiopia");
  const view = await render(<DataControlsScreen />);
  await fireEvent.press(view.getByRole("switch", { name: "settings.use_current_location" }));
  await waitFor(() =>
    expect(mockUpdateUser).toHaveBeenCalledWith({
      location_enabled: true,
      location: "Addis Ababa, Ethiopia",
    }),
  );
});

it("clears all chats only after a confirmation that says what stays", async () => {
  const view = await render(<DataControlsScreen />);
  await fireEvent.press(view.getByText("settings.delete_all_chats"));
  await waitFor(() => expect(mockDeleteAllChats).toHaveBeenCalledWith("tok"));
  expect(mockConfirm).toHaveBeenCalledWith(
    expect.objectContaining({
      title: "settings.delete_all_chats_title",
      message: "settings.delete_all_chats_body",
      destructive: true,
    }),
  );
});

it("keeps every chat when the clear is cancelled", async () => {
  mockConfirm.mockResolvedValue(false);
  const view = await render(<DataControlsScreen />);
  await fireEvent.press(view.getByText("settings.delete_all_chats"));
  await waitFor(() => expect(mockConfirm).toHaveBeenCalled());
  expect(mockDeleteAllChats).not.toHaveBeenCalled();
});

it("exports only after a confirmation that says what the file holds", async () => {
  const view = await render(<DataControlsScreen />);
  await fireEvent.press(view.getByText("settings.export"));
  await waitFor(() => expect(mockExport).toHaveBeenCalled());
  expect(mockConfirm).toHaveBeenCalledWith(
    expect.objectContaining({ title: "settings.export_confirm_title", message: "settings.export_confirm_body" }),
  );
});

it.each([
  // As the API sends it (docs/fixtures/error_codes.json).
  ["a refused export (one running, or a few an hour)", fixture.export_busy, "settings.export_busy"],
  ["any other failure", { status: 500, detail: "x" }, "settings.export_failed"],
])("says why an export did not happen: %s", async (_name, refusal, words) => {
  const { ApiRequestError } = jest.requireActual("@/lib/api/errorBody");
  const detail = refusal.detail;
  mockConfirm.mockResolvedValue(true);
  mockExport.mockRejectedValueOnce(new ApiRequestError(refusal.status, JSON.stringify({ detail })));
  const view = await render(<DataControlsScreen />);
  await fireEvent.press(view.getByText("settings.export"));
  await waitFor(() => expect(mockReportError).toHaveBeenCalledWith(null, words));
});

// A build without expo-sharing on Android (lib/shareFile.ts): an update is the fix, not "failed".
it("says to update the app when this build cannot share the export file", async () => {
  mockConfirm.mockResolvedValue(true);
  mockExport.mockRejectedValueOnce(new SharingUnavailableError());
  const view = await render(<DataControlsScreen />);
  await fireEvent.press(view.getByText("settings.export"));
  await waitFor(() => expect(mockReportError).toHaveBeenCalledWith(null, "common.share_needs_update"));
});

it("shows the export in progress with a way to cancel it", async () => {
  mockProgress = "exporting";
  const view = await render(<DataControlsScreen />);
  expect(view.getByText("settings.export_progress")).toBeTruthy();
  await fireEvent.press(view.getByText("common.cancel"));
  expect(mockCancelExport).toHaveBeenCalled();
});

it("deletes the account only after a confirmation that lists what is lost", async () => {
  mockDeleteAccount.mockResolvedValue("deleted");
  const view = await render(<DataControlsScreen />);
  await fireEvent.press(view.getByText("settings.delete"));
  await waitFor(() => expect(mockDeleteAccount).toHaveBeenCalled());
  expect(mockConfirm).toHaveBeenCalledWith(
    expect.objectContaining({ title: "delete.title", message: "delete.message", destructive: true }),
  );
  await waitFor(() => expect(mockReplace).toHaveBeenCalledWith("/login"));
});

it("closing the Apple sheet during delete shows no error and stays", async () => {
  mockDeleteAccount.mockResolvedValue("cancelled");
  const view = await render(<DataControlsScreen />);
  await fireEvent.press(view.getByText("settings.delete"));
  await waitFor(() => expect(mockDeleteAccount).toHaveBeenCalled());
  expect(mockReplace).not.toHaveBeenCalled();
  expect(mockReportError).not.toHaveBeenCalled();
});

it("a failed delete says so", async () => {
  mockDeleteAccount.mockResolvedValue("failed");
  const view = await render(<DataControlsScreen />);
  await fireEvent.press(view.getByText("settings.delete"));
  await waitFor(() =>
    expect(mockReportError).toHaveBeenCalledWith(null, "settings.delete_failed"),
  );
  expect(mockReplace).not.toHaveBeenCalled();
});

it("a delete refused while Recall is unavailable says so, to try again in a moment", async () => {
  mockDeleteAccount.mockResolvedValue("unavailable");
  const view = await render(<DataControlsScreen />);
  await fireEvent.press(view.getByText("settings.delete"));
  await waitFor(() =>
    expect(mockReportError).toHaveBeenCalledWith(null, "common.service_unavailable"),
  );
  expect(mockReplace).not.toHaveBeenCalled();
});

it("shows the account deletion in progress", async () => {
  mockProgress = "deleting";
  const view = await render(<DataControlsScreen />);
  expect(view.getByText("settings.delete_progress")).toBeTruthy();
});

it("shows when the account agreed to outside AI services, and only then", async () => {
  mockUser = { ...mockUser, ai_data_consent_at: "2026-10-19T09:00:00Z" };
  const view = await render(<DataControlsScreen />);
  expect(view.getByText("settings.ai_consent")).toBeTruthy();
  expect(view.getByText("settings.ai_consent_agreed")).toBeTruthy();

  mockUser = { ...mockUser, ai_data_consent_at: undefined };
  const older = await render(<DataControlsScreen />);
  expect(older.queryByText("settings.ai_consent")).toBeNull();
});

it("withdraws the agreement after a confirmation, so the consent screen comes back", async () => {
  mockUser = { ...mockUser, ai_data_consent_at: "2026-10-19T09:00:00Z" };
  const withdrawn = { ...mockUser, ai_data_consent_at: null };
  mockWithdraw.mockResolvedValue(withdrawn);
  const view = await render(<DataControlsScreen />);
  await fireEvent.press(view.getByText("settings.ai_consent"));
  await waitFor(() => expect(mockMergeUser).toHaveBeenCalledWith(withdrawn));
  expect(mockWithdraw).toHaveBeenCalledWith("tok");
  expect(mockWriteCachedUser).toHaveBeenCalledWith(withdrawn);
  expect(mockConfirm).toHaveBeenCalledWith(
    expect.objectContaining({
      title: "settings.ai_consent_withdraw_title",
      message: "settings.ai_consent_withdraw_body",
      confirmLabel: "settings.ai_consent_withdraw",
      destructive: true,
    }),
  );
});

it("keeps the agreement when the withdrawal is cancelled or fails", async () => {
  mockUser = { ...mockUser, ai_data_consent_at: "2026-10-19T09:00:00Z" };
  mockConfirm.mockResolvedValueOnce(false);
  const view = await render(<DataControlsScreen />);
  await fireEvent.press(view.getByText("settings.ai_consent"));
  await waitFor(() => expect(mockConfirm).toHaveBeenCalled());
  expect(mockWithdraw).not.toHaveBeenCalled();

  mockWithdraw.mockRejectedValue(new Error("offline"));
  await fireEvent.press(view.getByText("settings.ai_consent"));
  await waitFor(() =>
    expect(mockReportError).toHaveBeenCalledWith(null, "settings.ai_consent_withdraw_failed"),
  );
  expect(mockMergeUser).not.toHaveBeenCalled();
});
