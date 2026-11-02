// BUG FIX regression: LoginScreen used a single shared `busy` boolean for
// every sign-in button (Apple/Google/dev), so tapping ONE button made ALL
// visible buttons render their spinner simultaneously — reported live with a
// screenshot ("all buttons process instead of just the one that got
// pressed"). Native/config-heavy deps are stubbed so import-time stays safe,
// mirroring the mocking pattern established in components/__tests__.
import { act } from "react";
import { render, fireEvent } from "@testing-library/react-native";

import LoginScreen from "@/features/auth/screens/LoginScreen";
import { touchTargetHeight } from "@/lib/__tests__/support/touchTarget";

jest.mock("@/lib/haptics", () => ({
  tap: jest.fn(),
  selection: jest.fn(),
  notifySuccess: jest.fn(),
  notifyWarning: jest.fn(),
}));
jest.mock("expo-router", () => {
  const { Text } = jest.requireActual("react-native");
  return {
    Redirect: ({ href }: { href: string }) => <Text>{`redirect:${href}`}</Text>,
  };
});
jest.mock("expo-linear-gradient", () => {
  const { View } = jest.requireActual("react-native");
  return { LinearGradient: View };
});
jest.mock("@/lib/apple-auth", () => ({
  shouldShowAppleSignInButton: () => true,
  formatAppleSignInError: () => "generic",
}));
jest.mock("@/lib/google-auth", () => ({
  isExpoGo: () => false,
  formatGoogleSignInError: () => "generic",
}));
jest.mock("@/lib/config", () => ({
  config: { devAuthEnabled: false },
  isGoogleSignInConfigured: () => true,
  isGoogleWebClientConfigured: () => true,
}));
jest.mock("@/lib/legalUrls", () => ({
  getLegalPrivacyUrl: () => "https://example.com/privacy",
  getLegalTermsUrl: () => "https://example.com/terms",
}));

let resolveApple: (() => void) | undefined;
let resolveGoogle: (() => void) | undefined;
let mockSignedIn: { token: string; user: { ai_data_consent_at?: string | null } } | null = null;

jest.mock("@/contexts/AuthContext", () => ({
  useAuth: () => ({
    token: null,
    user: null,
    ...mockSignedIn,
    loading: false,
    onboarded: true,
    signInWithApple: () =>
      new Promise<void>((resolve) => {
        resolveApple = resolve;
      }),
    signInWithGoogle: () =>
      new Promise<void>((resolve) => {
        resolveGoogle = resolve;
      }),
    signInWithDev: () => Promise.resolve(),
  }),
}));

describe("LoginScreen", () => {
  beforeEach(() => {
    resolveApple = undefined;
    resolveGoogle = undefined;
    mockSignedIn = null;
  });

  it("reads the Terms and Privacy links, not the dot drawn between them", async () => {
    const { getByRole, queryByText, getByText } = await render(<LoginScreen />);
    expect(getByRole("link", { name: "login.terms" })).toBeOnTheScreen();
    expect(getByRole("link", { name: "login.privacy" })).toBeOnTheScreen();
    expect(getByText("·", { includeHiddenElements: true })).toBeTruthy();
    expect(queryByText("·")).toBeNull();
    // A 12pt line is about 17pt tall; hitSlop makes each link a 44pt target.
    expect(touchTargetHeight(getByRole("link", { name: "login.terms" }))).toBeGreaterThanOrEqual(44);
    expect(touchTargetHeight(getByRole("link", { name: "login.privacy" }))).toBeGreaterThanOrEqual(44);
  });

  it("says beside the buttons that continuing agrees, with the Terms and Privacy links", async () => {
    // Apple 5.1.2(i): the line sits between the sign-in buttons and the two links, so the
    // tap that signs in is the agreement (features/auth/api.ts sends it with the sign-in).
    const { getByText, getByRole, toJSON } = await render(<LoginScreen />);
    expect(getByText("login.consent_line")).toBeOnTheScreen();
    expect(getByRole("link", { name: "login.terms" })).toBeOnTheScreen();
    expect(getByRole("link", { name: "login.privacy" })).toBeOnTheScreen();
    const order = JSON.stringify(toJSON());
    const at = (text: string) => order.indexOf(`"${text}"`);
    expect(at("login.google")).toBeLessThan(at("login.consent_line"));
    expect(at("login.apple")).toBeLessThan(at("login.consent_line"));
    expect(at("login.consent_line")).toBeLessThan(at("login.terms"));
  });

  it("sends a sign-in the server answered without the agreement (an older API) to the AI consent screen", async () => {
    mockSignedIn = { token: "tok", user: { ai_data_consent_at: null } };
    const { getByText } = await render(<LoginScreen />);
    expect(getByText("redirect:/consent")).toBeOnTheScreen();
  });

  it("sends an account that already agreed straight to the chat", async () => {
    mockSignedIn = { token: "tok", user: { ai_data_consent_at: "2026-10-19T12:00:00Z" } };
    const { getByText } = await render(<LoginScreen />);
    expect(getByText("redirect:/")).toBeOnTheScreen();
  });

  it("BUG FIX regression: only the tapped button shows its spinner, not every visible button", async () => {
    const { getByLabelText, getByText, queryByText } = await render(<LoginScreen />);

    // Both buttons rendered with their normal (non-busy) content.
    expect(getByText("app.name")).toBeOnTheScreen();
    expect(getByLabelText("app.name")).toBeOnTheScreen();
    expect(getByText("login.apple")).toBeOnTheScreen();
    expect(getByText("login.google")).toBeOnTheScreen();

    await act(async () => {
      fireEvent.press(getByText("login.apple"));
    });

    // The tapped (Apple) button's label is replaced by its spinner...
    expect(queryByText("login.apple")).toBeNull();
    // ...but the Google button, which was never pressed, must still show its
    // own label/icon, not a spinner too.
    expect(getByText("login.google")).toBeOnTheScreen();

    await act(async () => {
      resolveApple?.();
    });
  });

  it("restores the tapped button's label after sign-in resolves", async () => {
    const { getByText, queryByText } = await render(<LoginScreen />);

    await act(async () => {
      fireEvent.press(getByText("login.google"));
    });
    expect(queryByText("login.google")).toBeNull();

    await act(async () => {
      resolveGoogle?.();
    });
    expect(getByText("login.google")).toBeOnTheScreen();
  });
});
