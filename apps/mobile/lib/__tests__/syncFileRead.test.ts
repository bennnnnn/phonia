import { readTextFileSync } from "@/lib/syncFileRead";

const mockFiles = new Map<string, string>();
let mockBroken = false;
jest.mock("expo-file-system", () => ({
  Paths: { document: "file:///docs/", cache: "file:///cache/" },
  File: class {
    private readonly path: string;
    constructor(directory: string, name: string) {
      this.path = `${directory}${name}`;
    }
    get exists() {
      if (mockBroken) throw new Error("unreadable");
      return mockFiles.has(this.path);
    }
    textSync() {
      return mockFiles.get(this.path) ?? "";
    }
  },
}));

beforeEach(() => {
  mockFiles.clear();
  mockBroken = false;
});

describe("readTextFileSync", () => {
  it("reads a file from the documents or the cache directory", () => {
    mockFiles.set("file:///docs/pref.txt", "dark");
    mockFiles.set("file:///cache/user.json", "{}");
    expect(readTextFileSync("document", "pref.txt")).toBe("dark");
    expect(readTextFileSync("cache", "user.json")).toBe("{}");
  });

  it("answers null for a missing or unreadable file instead of failing the launch", () => {
    expect(readTextFileSync("document", "missing.txt")).toBeNull();
    mockBroken = true;
    expect(readTextFileSync("document", "pref.txt")).toBeNull();
  });
});
