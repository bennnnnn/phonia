import Constants from "expo-constants";

import {
  appleConsentForAccountDelete,
  shouldShowAppleSignInButton,
  signInWithAppleCredentials,
} from "@/lib/apple-auth";

jest.mock("expo-constants", () => ({
  __esModule: true,
  default: { expoConfig: { extra: {} } },
}));

jest.mock("react-native", () => ({
  Platform: { OS: "ios" },
}));

let mockExpoGo = false;
jest.mock("@/lib/expoRuntime", () => ({ isExpoGo: () => mockExpoGo }));

const mockSignInAsync = jest.fn();
const mockIsAvailable = jest.fn(async () => true);
jest.mock("expo-apple-authentication", () => ({
  isAvailableAsync: () => mockIsAvailable(),
  signInAsync: (...args: unknown[]) => mockSignInAsync(...args),
  AppleAuthenticationScope: { FULL_NAME: 0, EMAIL: 1 },
}));

jest.mock("expo-crypto", () => ({
  CryptoDigestAlgorithm: { SHA256: "SHA-256" },
  getRandomBytes: jest.fn(() => new Uint8Array([0, 1, 254, 255])),
  digestStringAsync: jest.fn(async (_algorithm: string, value: string) => `sha256(${value})`),
}));

describe("signInWithAppleCredentials", () => {
  it("binds Apple's token to this sign-in with a hashed nonce and keeps the raw one", async () => {
    mockSignInAsync.mockResolvedValue({
      identityToken: "apple.id.token",
      fullName: { givenName: "Ada", familyName: "Lovelace" },
    });

    const result = await signInWithAppleCredentials();

    // Apple gets SHA-256(raw) and echoes it in the token; only the server,
    // which receives the raw value, can match the two.
    expect(mockSignInAsync).toHaveBeenCalledWith(
      expect.objectContaining({ nonce: "sha256(0001feff)" }),
    );
    expect(result).toEqual({
      idToken: "apple.id.token",
      name: "Ada Lovelace",
      nonce: "0001feff",
    });
  });
});

describe("appleConsentForAccountDelete", () => {
  beforeEach(() => {
    mockSignInAsync.mockReset();
    mockIsAvailable.mockResolvedValue(true);
  });

  it("asks Apple for a fresh code and no personal scopes", async () => {
    mockSignInAsync.mockResolvedValue({ identityToken: "t", authorizationCode: " code-1 " });
    await expect(appleConsentForAccountDelete()).resolves.toEqual({ kind: "code", code: "code-1" });
    expect(mockSignInAsync).toHaveBeenCalledWith({ requestedScopes: [] });
  });

  it("closing the sheet is a cancel", async () => {
    mockSignInAsync.mockRejectedValue(
      Object.assign(new Error("The user canceled the authorization attempt"), {
        code: "ERR_REQUEST_CANCELED",
      }),
    );
    await expect(appleConsentForAccountDelete()).resolves.toEqual({ kind: "cancelled" });
  });

  it.each([
    ["Apple returns no code", () => mockSignInAsync.mockResolvedValue({ authorizationCode: null })],
    ["Apple fails", () => mockSignInAsync.mockRejectedValue(new Error("ERR_REQUEST_FAILED"))],
    ["Sign in with Apple is off", () => mockIsAvailable.mockResolvedValue(false)],
  ])("%s: the delete goes ahead without a code", async (_name, arrange) => {
    arrange();
    await expect(appleConsentForAccountDelete()).resolves.toEqual({ kind: "unavailable" });
  });
});

function setExtra(extra: Record<string, unknown>): void {
  (Constants as unknown as { expoConfig: { extra: Record<string, unknown> } }).expoConfig = {
    extra,
  };
}

describe("shouldShowAppleSignInButton", () => {
  it("shows the Apple button on iOS", () => {
    setExtra({ appleSignIn: true });
    expect(shouldShowAppleSignInButton()).toBe(true);
    setExtra({});
    expect(shouldShowAppleSignInButton()).toBe(true);
  });

  it("hides it in a simulator build that left Sign in with Apple out", () => {
    setExtra({ appleSignIn: false });
    expect(shouldShowAppleSignInButton()).toBe(false);
  });

  it("hides it in Expo Go, whose Apple token the server refuses", () => {
    setExtra({});
    mockExpoGo = true;
    try {
      expect(shouldShowAppleSignInButton()).toBe(false);
    } finally {
      mockExpoGo = false;
    }
  });
});
