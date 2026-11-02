import {
  clearSettledStatuses,
  readSettledStatuses,
  writeSettledStatuses,
  type SettledStatus,
} from "@/features/attachments/model/attachmentStatusFile";

const mockFiles = new Map<string, string>();
jest.mock("expo-file-system/legacy", () => ({
  cacheDirectory: "file:///cache/",
  getInfoAsync: async (path: string) => ({ exists: mockFiles.has(path) }),
  readAsStringAsync: async (path: string) => mockFiles.get(path) ?? "",
  writeAsStringAsync: async (path: string, contents: string) => {
    mockFiles.set(path, contents);
  },
  deleteAsync: async (path: string) => {
    mockFiles.delete(path);
  },
}));

const FILE = "file:///cache/recall-attachment-status.json";

function tokenFor(account: string): string {
  return `h.${btoa(JSON.stringify({ sub: account }))}.s`;
}

const ready: SettledStatus = { indexed: true, failed: false, fileName: "notes.pdf" };

beforeEach(() => mockFiles.clear());

it("keeps the newest 500 statuses, for the account that read them", async () => {
  const statuses = new Map<string, SettledStatus>();
  for (let i = 0; i < 520; i += 1) statuses.set(`file-${i}`, ready);
  await writeSettledStatuses(tokenFor("user-a"), statuses);
  const read = await readSettledStatuses(tokenFor("user-a"));
  expect(read.size).toBe(500);
  expect(read.has("file-19")).toBe(false);
  expect(read.get("file-519")).toEqual(ready);
  expect((await readSettledStatuses(tokenFor("user-b"))).size).toBe(0);
});

it("reads a damaged file, or one without an account, as empty", async () => {
  mockFiles.set(FILE, "{not json");
  expect((await readSettledStatuses(tokenFor("user-a"))).size).toBe(0);
  mockFiles.set(FILE, JSON.stringify({ user_id: "user-a", statuses: { a: { indexed: "yes" }, b: ready } }));
  expect([...(await readSettledStatuses(tokenFor("user-a"))).keys()]).toEqual(["b"]);
  // A token with no readable account neither reads nor writes.
  expect((await readSettledStatuses("opaque")).size).toBe(0);
  await clearSettledStatuses();
  await writeSettledStatuses("opaque", new Map([["c", ready]]));
  expect(mockFiles.has(FILE)).toBe(false);
});
