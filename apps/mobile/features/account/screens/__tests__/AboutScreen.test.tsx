import { act, fireEvent, render } from "@testing-library/react-native";

import AboutScreen from "@/features/account/screens/AboutScreen";

const mockOpenUrl = jest.fn();
const mockReportError = jest.fn();
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
}));
jest.mock("@/lib/linkSchemePolicy", () => ({
  openAllowedUrl: (...args: unknown[]) => mockOpenUrl(...args),
}));

beforeEach(() => {
  jest.clearAllMocks();
  mockConfig.supportEmail = null;
});

it("shows the legal pages, the licenses and the version, and no help rows", async () => {
  const view = await render(<AboutScreen />);
  expect(view.getByText("privacy.title")).toBeTruthy();
  expect(view.getByText("terms.title")).toBeTruthy();
  expect(view.getByText("settings.licenses")).toBeTruthy();
  expect(view.getByText("2.3.4")).toBeTruthy();
  expect(view.queryByText("settings.report_problem")).toBeNull();
  expect(view.queryByText("UI kit")).toBeNull();
});

it("opens the privacy policy", async () => {
  mockOpenUrl.mockResolvedValue(true);
  const view = await render(<AboutScreen />);
  await act(async () => {
    fireEvent.press(view.getByText("privacy.title"));
  });
  expect(mockOpenUrl).toHaveBeenCalledWith("https://recall.test/privacy");
  expect(mockReportError).not.toHaveBeenCalled();
});

it("says so when a legal page cannot be opened", async () => {
  mockOpenUrl.mockResolvedValue(false);
  const view = await render(<AboutScreen />);
  await act(async () => {
    fireEvent.press(view.getByText("terms.title"));
  });
  expect(mockReportError).toHaveBeenCalledWith(null, "settings.link_failed");
});
