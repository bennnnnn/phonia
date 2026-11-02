import { act, renderHook } from "@testing-library/react-native";
import { Platform } from "react-native";

import { useDataControls } from "@/features/account/hooks/useDataControls";
import { ApiRequestError } from "@/lib/api/errorBody";
import type { AppleDeleteConsent } from "@/lib/apple-auth";

const mockExportText = jest.fn();
const mockShare = jest.fn();
const mockDeleteAccount = jest.fn();
const mockSignOut = jest.fn();
const mockAppleConsent = jest.fn<Promise<AppleDeleteConsent>, []>();
let mockUser: { apple_linked?: boolean } | null = null;

jest.mock("@/contexts/AuthContext", () => ({
  useAuth: () => ({
    token: "tok",
    user: mockUser,
    signOut: mockSignOut,
    setIgnoreUnauthorized: jest.fn(),
  }),
}));
jest.mock("@/lib/api", () => ({
  api: {
    exportDataText: (...args: unknown[]) => mockExportText(...args),
    deleteAccount: (...args: unknown[]) => mockDeleteAccount(...args),
  },
}));
jest.mock("@/lib/apple-auth", () => ({
  appleConsentForAccountDelete: () => mockAppleConsent(),
}));
jest.mock("@/lib/exportData", () => ({
  formatExportJsonForShare: (raw: string) => raw,
  shareAccountExport: (...args: unknown[]) => mockShare(...args),
}));
jest.mock("@/lib/accountDelete", () => ({
  ...jest.requireActual("@/lib/accountDelete"),
  isAccountDeleteComplete: () => false,
}));

beforeEach(() => {
  jest.clearAllMocks();
  jest.replaceProperty(Platform, "OS", "ios");
  mockUser = null;
  mockDeleteAccount.mockResolvedValue(undefined);
  mockSignOut.mockResolvedValue(undefined);
});

afterEach(() => jest.restoreAllMocks());

it("exports and shares the file", async () => {
  mockExportText.mockResolvedValue("{}");
  const { result } = await renderHook(() => useDataControls());
  let done: boolean | undefined;
  await act(async () => {
    done = await result.current.exportData();
  });
  expect(done).toBe(true);
  expect(mockShare).toHaveBeenCalledWith("{}");
  expect(result.current.progress).toBe("idle");
});

it("cancelling stops the request and shares nothing", async () => {
  mockExportText.mockImplementation(
    (_token: string, signal: AbortSignal) =>
      new Promise((_resolve, reject) => {
        signal.addEventListener("abort", () => reject(new Error("Aborted")));
      }),
  );
  const { result } = await renderHook(() => useDataControls());
  let pending: Promise<boolean> | undefined;
  await act(async () => {
    pending = result.current.exportData();
  });
  expect(result.current.progress).toBe("exporting");
  await act(async () => {
    result.current.cancelExport();
  });
  await expect(pending).resolves.toBe(false);
  expect(mockShare).not.toHaveBeenCalled();
  expect(result.current.progress).toBe("idle");
});

async function runDelete() {
  const { result } = await renderHook(() => useDataControls());
  let outcome: string | undefined;
  await act(async () => {
    outcome = await result.current.deleteAccount();
  });
  return { outcome, progress: result.current.progress };
}

it("an Apple-linked account on iOS sends Apple's fresh code so its grant is revoked", async () => {
  mockUser = { apple_linked: true };
  mockAppleConsent.mockResolvedValue({ kind: "code", code: "apple-code" });
  const { outcome } = await runDelete();
  expect(outcome).toBe("deleted");
  expect(mockDeleteAccount).toHaveBeenCalledWith("tok", "apple-code");
  expect(mockSignOut).toHaveBeenCalled();
});

it("closing the Apple sheet keeps the account", async () => {
  mockUser = { apple_linked: true };
  mockAppleConsent.mockResolvedValue({ kind: "cancelled" });
  const { outcome, progress } = await runDelete();
  expect(outcome).toBe("cancelled");
  expect(progress).toBe("idle");
  expect(mockDeleteAccount).not.toHaveBeenCalled();
  expect(mockSignOut).not.toHaveBeenCalled();
});

it("deletes without a code when Sign in with Apple cannot run on this build", async () => {
  mockUser = { apple_linked: true };
  mockAppleConsent.mockResolvedValue({ kind: "unavailable" });
  const { outcome } = await runDelete();
  expect(outcome).toBe("deleted");
  expect(mockDeleteAccount).toHaveBeenCalledWith("tok", null);
});

it.each([
  ["a Google account on iOS", "ios", { apple_linked: false }],
  ["an Apple-linked account on Android", "android", { apple_linked: true }],
] as const)("%s deletes as before, without asking Apple", async (_name, os, user) => {
  jest.replaceProperty(Platform, "OS", os);
  mockUser = user;
  const { outcome } = await runDelete();
  expect(outcome).toBe("deleted");
  expect(mockAppleConsent).not.toHaveBeenCalled();
  expect(mockDeleteAccount).toHaveBeenCalledWith("tok", null);
});

it("a failed delete reports failure and leaves the account screen usable", async () => {
  mockDeleteAccount.mockRejectedValue(new Error("offline"));
  const { outcome, progress } = await runDelete();
  expect(outcome).toBe("failed");
  expect(progress).toBe("idle");
  expect(mockSignOut).not.toHaveBeenCalled();
});

const UNAVAILABLE = JSON.stringify({
  detail: { code: "unavailable", message: "Service temporarily unavailable. Please retry shortly." },
});

// Refused while Redis is down (the usage carry-over, the session purge), nothing was
// deleted and a retry in a moment works: it said "Could not delete your account".
it.each([
  ["the API's outage", new ApiRequestError(503, UNAVAILABLE), "unavailable"],
  ["a gateway's 502 during a deploy", new ApiRequestError(502, "<html>Bad gateway</html>"), "unavailable"],
  ["a server error", new ApiRequestError(500, JSON.stringify({ detail: "Internal Server Error" })), "failed"],
])("a delete refused by %s stays signed in and says why", async (_name, error, outcome) => {
  mockDeleteAccount.mockRejectedValue(error);
  const run = await runDelete();
  expect(run.outcome).toBe(outcome);
  expect(run.progress).toBe("idle");
  expect(mockSignOut).not.toHaveBeenCalled();
});
