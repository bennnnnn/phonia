import { act, renderHook } from "@testing-library/react-native";

import { useSettingsProposal } from "@/features/chat/hooks/useSettingsProposal";

const mockConfirm = jest.fn();
const mockMergeUser = jest.fn();
const mockSetPreference = jest.fn(async () => {});

jest.mock("@/lib/api", () => ({
  api: { confirmSettingsProposal: (...args: unknown[]) => mockConfirm(...args) },
}));
jest.mock("@/contexts/AuthContext", () => ({
  useAuth: () => ({ token: "token-a", mergeUser: mockMergeUser }),
}));
jest.mock("@/contexts/AppearanceContext", () => ({
  useAppearance: () => ({ setPreference: mockSetPreference }),
}));
jest.mock("@/lib/cachedUser", () => ({ writeCachedUser: jest.fn(async () => {}) }));

beforeEach(() => {
  jest.clearAllMocks();
});

describe("useSettingsProposal", () => {
  it("applies the theme the card names", async () => {
    mockConfirm.mockResolvedValue({
      user: { id: "u1" },
      appearance: "dark",
      applied: [{ field: "appearance", value: "dark", label: "Dark" }],
    });
    const { result } = await renderHook(() =>
      useSettingsProposal({
        proposal_id: "a1",
        changes: [{ field: "appearance", value: "dark", label: "Dark" }],
      }),
    );
    await act(async () => {
      await result.current.confirm();
    });
    expect(mockConfirm).toHaveBeenCalledWith("token-a", "a1");
    expect(mockSetPreference).toHaveBeenCalledWith("dark");
  });
});
