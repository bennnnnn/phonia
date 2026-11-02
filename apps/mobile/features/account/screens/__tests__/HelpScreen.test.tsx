import { act, fireEvent, render } from "@testing-library/react-native";

import HelpScreen from "@/features/account/screens/HelpScreen";

const mockOpenUrl = jest.fn();
const mockReportError = jest.fn();
const mockReportWarning = jest.fn();
const mockSetString = jest.fn(async (_text: string) => true);
const mockConfig: { supportEmail: string | null } = { supportEmail: null };

jest.mock("expo-constants", () => ({ expoConfig: { version: "2.3.4" } }));
jest.mock("expo-router", () => ({ Redirect: () => null, router: { push: jest.fn() } }));
jest.mock("@/contexts/AuthContext", () => ({
  useAuth: () => ({ token: "tok", user: { locale: "en" } }),
}));
jest.mock("@/contexts/actionFeedbackCore", () => ({ useActionFeedbackOptional: () => null }));
jest.mock("@/hooks/useModels", () => ({ useModels: () => ({ isPaid: false }) }));
jest.mock("@/lib/config", () => ({
  get config() {
    return mockConfig;
  },
}));
jest.mock("@/lib/legalUrls", () => ({
  getLegalPrivacyUrl: () => "https://recall.test/privacy",
  getLegalTermsUrl: () => "https://recall.test/terms",
}));
jest.mock("@/lib/reportRecoverableError", () => ({
  reportRecoverableError: (...args: unknown[]) => mockReportError(...args),
  reportRecoverableWarning: (...args: unknown[]) => mockReportWarning(...args),
}));
jest.mock("expo-clipboard", () => ({ setStringAsync: (text: string) => mockSetString(text) }));
jest.mock("@/lib/haptics", () => ({ notifySuccess: jest.fn() }));
jest.mock("@/lib/linkSchemePolicy", () => ({
  openAllowedUrl: (...args: unknown[]) => mockOpenUrl(...args),
}));

beforeEach(() => {
  jest.clearAllMocks();
  mockConfig.supportEmail = null;
});

it("writes every help row to the support address, and no legal pages", async () => {
  mockConfig.supportEmail = "help@recall.test";
  mockOpenUrl.mockResolvedValue(true);
  const view = await render(<HelpScreen />);
  expect(view.queryByText("privacy.title")).toBeNull();
  for (const row of ["settings.contact_support", "settings.report_problem", "settings.send_feedback"]) {
    mockOpenUrl.mockClear();
    await act(async () => {
      fireEvent.press(view.getByText(row));
    });
    const url = mockOpenUrl.mock.calls[0][0] as string;
    expect(url.startsWith("mailto:help@recall.test?subject=")).toBe(true);
    expect(decodeURIComponent(url)).toContain(`settings.contact_support_subject: ${row}`);
    expect(decodeURIComponent(url)).toContain("settings.about_version: 2.3.4");
  }
});

it("says support is not set up, instead of a share sheet that reaches nobody", async () => {
  const view = await render(<HelpScreen />);
  expect(view.getByText("settings.support_unavailable")).toBeTruthy();
  expect(view.queryByText("settings.contact_support")).toBeNull();
  expect(view.queryByText("settings.report_problem")).toBeNull();
  expect(view.queryByText("settings.send_feedback")).toBeNull();
});

it("copies the address for any email app when no mail app opens", async () => {
  mockConfig.supportEmail = "help@recall.test";
  mockOpenUrl.mockResolvedValue(false);
  const view = await render(<HelpScreen />);
  await act(async () => {
    fireEvent.press(view.getByText("settings.contact_support"));
  });
  expect(mockSetString).toHaveBeenCalledWith("help@recall.test");
  expect(mockReportWarning).toHaveBeenCalledWith(null, "settings.mail_copied");
  expect(mockReportError).not.toHaveBeenCalled();
});

it.each(["settings.report_problem", "settings.send_feedback"])(
  "%s copies the address with the subject and the version, when no mail app opens",
  async (row) => {
    mockConfig.supportEmail = "help@recall.test";
    mockOpenUrl.mockResolvedValue(false);
    const view = await render(<HelpScreen />);
    await act(async () => {
      fireEvent.press(view.getByText(row));
    });
    const copied = mockSetString.mock.calls[0]![0];
    expect(copied.startsWith("help@recall.test\n\n")).toBe(true);
    expect(copied).toContain(`settings.contact_support_subject: ${row}`);
    expect(copied).toContain("settings.about_version: 2.3.4");
    expect(mockReportWarning).toHaveBeenCalledWith(null, "settings.mail_copied_report");
  },
);

it("says it could not open mail when the copy fails too", async () => {
  mockConfig.supportEmail = "help@recall.test";
  mockOpenUrl.mockResolvedValue(false);
  mockSetString.mockRejectedValueOnce(new Error("denied"));
  const view = await render(<HelpScreen />);
  await act(async () => {
    fireEvent.press(view.getByText("settings.report_problem"));
  });
  expect(mockReportError).toHaveBeenCalledWith(null, "settings.link_failed");
  expect(mockReportWarning).not.toHaveBeenCalled();
});
