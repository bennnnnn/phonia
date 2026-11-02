import { render } from "@testing-library/react-native";

import { AiConsentRedirect } from "@/features/auth/components/AiConsentRedirect";

const mockReplace = jest.fn();
let mockPathname = "/";
let mockNavigationKey: string | undefined = "root";
let mockUser: { ai_data_consent_at?: string | null } | null = null;

jest.mock("expo-router", () => ({
  useRouter: () => ({ replace: mockReplace }),
  usePathname: () => mockPathname,
  useRootNavigationState: () => (mockNavigationKey ? { key: mockNavigationKey } : undefined),
}));
jest.mock("@/contexts/AuthContext", () => ({
  useAuthOptional: () => ({ user: mockUser }),
}));

describe("AiConsentRedirect", () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockPathname = "/";
    mockNavigationKey = "root";
    mockUser = { ai_data_consent_at: null };
  });

  it("sends an account that has not agreed from the chat to the consent screen", async () => {
    await render(<AiConsentRedirect />);
    expect(mockReplace).toHaveBeenCalledWith("/consent");
  });

  it("also covers a screen opened from a notification or deep link", async () => {
    mockPathname = "/todos";
    await render(<AiConsentRedirect />);
    expect(mockReplace).toHaveBeenCalledWith("/consent");
  });

  it("waits until the root navigator has mounted", async () => {
    mockNavigationKey = undefined;
    await render(<AiConsentRedirect />);
    expect(mockReplace).not.toHaveBeenCalled();
  });

  it.each([
    ["an account that agreed", { ai_data_consent_at: "2026-10-19T12:00:00Z" }, "/"],
    ["an unknown answer from an older server or cache", {}, "/"],
    ["a signed-out user", null, "/"],
    ["the consent screen itself", { ai_data_consent_at: null }, "/consent"],
    ["the sign-in screen", { ai_data_consent_at: null }, "/login"],
  ])("leaves %s alone", async (_label, user, pathname) => {
    mockUser = user;
    mockPathname = pathname;
    await render(<AiConsentRedirect />);
    expect(mockReplace).not.toHaveBeenCalled();
  });
});
