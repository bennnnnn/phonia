import { useLayoutEffect } from "react";
import { act, render, waitFor } from "@testing-library/react-native";

import { ModelsProvider, useModelsContext } from "@/contexts/ModelsContext";
import { api, type ModelInfo } from "@/lib/api";
import { readCachedModels, writeCachedModels } from "@/lib/cachedModels";

let mockSession = 1;
let mockToken: string | null = "token-a";
let mockUserId: string | null = "account-a";
let mockEnabledModels: string[] | null = null;
// Stable, as the provider keeps it.
const mockGetToken = () => mockToken;
jest.mock("@/contexts/accountSession", () => ({
  useAccountSession: () => ({
    account: mockToken && mockUserId ? `${mockUserId}:${mockSession}` : null,
    getToken: mockGetToken,
  }),
}));
jest.mock("@/contexts/AuthContext", () => ({
  useAuthOptional: () => ({
    token: mockToken,
    user: mockUserId ? { id: mockUserId, plan: "free", enabled_models: mockEnabledModels } : null,
  }),
}));
jest.mock("@/lib/auth", () => ({ getSessionGeneration: () => mockSession }));
jest.mock("@/lib/api", () => ({ api: { listModels: jest.fn() } }));
jest.mock("@/lib/cachedModels", () => ({
  readCachedModels: jest.fn(),
  writeCachedModels: jest.fn(),
}));

const everyday: ModelInfo = {
  id: "free-chat", label: "Everyday", description: "", tier: "fast",
  plan_access: "free", available: true,
};
const reasoning: ModelInfo = {
  id: "smart-chat", label: "Reasoning", description: "", tier: "smart",
  plan_access: "pro", available: true,
};
const added: ModelInfo = {
  id: "glm-5.3", label: "Added on the server", description: "", tier: "smart",
  plan_access: "pro", available: true,
};

let current: ReturnType<typeof useModelsContext>;
function Probe() {
  const value = useModelsContext();
  useLayoutEffect(() => { current = value; }, [value]);
  return null;
}
function Screen() {
  return <ModelsProvider><Probe /></ModelsProvider>;
}
const shownIds = () => current.models.map((model) => model.id);

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((done) => { resolve = done; });
  return { promise, resolve };
}

beforeEach(() => {
  jest.clearAllMocks();
  mockSession = 1; mockToken = "token-a"; mockUserId = "account-a"; mockEnabledModels = null;
  jest.mocked(readCachedModels).mockResolvedValue(null);
  jest.mocked(writeCachedModels).mockResolvedValue(undefined);
  jest.mocked(api.listModels).mockRejectedValue(new Error("offline"));
});

it("renders the cached catalog when /models fails", async () => {
  jest.mocked(readCachedModels).mockResolvedValue([everyday, reasoning]);
  await render(<Screen />);
  await waitFor(() => expect(shownIds()).toEqual(["free-chat", "smart-chat"]));
  expect(readCachedModels).toHaveBeenCalledWith("account-a");
  expect(api.listModels).toHaveBeenCalledWith("token-a");
  expect(current.labelFor("smart-chat")).toBe("Reasoning");
  expect(writeCachedModels).not.toHaveBeenCalled();
});

it("falls back to free-chat alone on a fresh install when /models fails", async () => {
  await render(<Screen />);
  await waitFor(() => expect(api.listModels).toHaveBeenCalled());
  await act(async () => {});
  expect(shownIds()).toEqual(["free-chat"]);
  expect(current.models[0]).toMatchObject({ plan_access: "free", available: true });
  // The composer can still send: Auto first, then the one free model.
  expect(current.preferences).toEqual(["auto", "free-chat"]);
});

it("persists a successful /models response for the signed-in account", async () => {
  jest.mocked(api.listModels).mockResolvedValue([everyday, added]);
  await render(<Screen />);
  await waitFor(() => expect(shownIds()).toEqual(["free-chat", "glm-5.3"]));
  expect(writeCachedModels).toHaveBeenCalledWith("account-a", [everyday, added]);
});

it("keeps a fresh /models response over a slower read of the cache", async () => {
  const disk = deferred<ModelInfo[] | null>();
  jest.mocked(readCachedModels).mockReturnValue(disk.promise);
  jest.mocked(api.listModels).mockResolvedValue([everyday, added]);
  await render(<Screen />);
  await waitFor(() => expect(shownIds()).toEqual(["free-chat", "glm-5.3"]));
  await act(async () => { disk.resolve([everyday, reasoning]); });
  expect(shownIds()).toEqual(["free-chat", "glm-5.3"]);
});

it("does not show one account's catalog to the next", async () => {
  jest.mocked(api.listModels).mockResolvedValueOnce([everyday, reasoning]);
  const ui = await render(<Screen />);
  await waitFor(() => expect(shownIds()).toEqual(["free-chat", "smart-chat"]));
  mockSession++; mockToken = "token-b"; mockUserId = "account-b";
  await ui.rerender(<Screen />);
  expect(shownIds()).toEqual(["free-chat"]);
  await waitFor(() => expect(readCachedModels).toHaveBeenCalledWith("account-b"));
  await waitFor(() => expect(api.listModels).toHaveBeenCalledWith("token-b"));
  expect(shownIds()).toEqual(["free-chat"]);
});

it("does not fetch /models again when the access token rotates", async () => {
  jest.mocked(api.listModels).mockResolvedValue([everyday, reasoning]);
  const ui = await render(<Screen />);
  await waitFor(() => expect(shownIds()).toEqual(["free-chat", "smart-chat"]));
  expect(api.listModels).toHaveBeenCalledTimes(1);

  mockToken = "token-a-refreshed";
  await ui.rerender(<Screen />);
  await act(async () => {});
  expect(api.listModels).toHaveBeenCalledTimes(1);

  await act(async () => {
    await current.refresh();
  });
  expect(api.listModels).toHaveBeenLastCalledWith("token-a-refreshed");
});

it("does not persist a /models response that lands after signout", async () => {
  const late = deferred<ModelInfo[]>();
  jest.mocked(api.listModels).mockReturnValue(late.promise);
  const ui = await render(<Screen />);
  mockSession++; mockToken = null; mockUserId = null;
  await ui.rerender(<Screen />);
  await act(async () => { late.resolve([everyday, reasoning]); });
  expect(writeCachedModels).not.toHaveBeenCalled();
  expect(shownIds()).toEqual(["free-chat"]);
});

// Settings → Model showed every switch off under Auto while Auto used them.
it.each([
  [null, ["free-chat"]],
  [["auto"], ["free-chat"]],
  [["auto", "free-chat"], ["free-chat"]],
])("saved %j switches on the models Auto uses: %j", async (saved, onIds) => {
  mockEnabledModels = saved;
  jest.mocked(api.listModels).mockResolvedValue([everyday, reasoning]);
  await render(<Screen />);
  await waitFor(() => expect(shownIds()).toEqual(["free-chat", "smart-chat"]));
  expect(current.autoEnabled).toBe(true);
  expect([...current.modelEnabledSet]).toEqual(onIds);
});

