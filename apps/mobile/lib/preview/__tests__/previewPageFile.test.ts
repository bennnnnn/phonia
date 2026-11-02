import { digestStringAsync } from "expo-crypto";
import * as fileSystem from "expo-file-system/legacy";

import type { PreviewPage } from "@/lib/preview/previewPage";
import {
  forgetPreviewPageFile,
  previewPageFile,
  readyPreviewPageFile,
} from "@/lib/preview/previewPageFile";
import {
  readVendorLibraries,
  removeSupersededVendorCopies,
  type VendorLibrary,
} from "@/lib/vendorAssets";

/** The cache directory as files on disk: path → contents. */
const mockFiles = new Map<string, string>();
const mockStorage = { cacheDirectory: "file:///cache/" as string | null };
const mockHashes: Partial<Record<VendorLibrary, string>> = {};
const mockSources: Partial<Record<VendorLibrary, string>> = {};
let mockIds = 0;

jest.mock("expo-file-system/legacy", () => ({
  get cacheDirectory() {
    return mockStorage.cacheDirectory;
  },
  getInfoAsync: jest.fn(async (uri: string) =>
    mockFiles.has(uri)
      ? { exists: true, isDirectory: false, size: mockFiles.get(uri)!.length, uri }
      : { exists: false, isDirectory: false, uri },
  ),
  makeDirectoryAsync: jest.fn(async () => undefined),
  writeAsStringAsync: jest.fn(async (uri: string, contents: string) => {
    mockFiles.set(uri, contents);
  }),
  // Like iOS: a move onto an existing file fails.
  moveAsync: jest.fn(async ({ from, to }: { from: string; to: string }) => {
    if (mockFiles.has(to)) throw new Error(`${to} exists`);
    mockFiles.set(to, mockFiles.get(from) ?? "");
    mockFiles.delete(from);
  }),
  readDirectoryAsync: jest.fn(async (dir: string) =>
    [...mockFiles.keys()].filter((uri) => uri.startsWith(dir)).map((uri) => uri.slice(dir.length)),
  ),
  deleteAsync: jest.fn(async (uri: string) => {
    mockFiles.delete(uri);
  }),
}));

jest.mock("expo-crypto", () => {
  const { createHash } = jest.requireActual<{
    createHash(name: string): { update(value: string): { digest(encoding: string): string } };
  }>("node:crypto");
  return {
    CryptoDigestAlgorithm: { SHA256: "SHA-256" },
    digestStringAsync: jest.fn(async (_algorithm: string, value: string) =>
      createHash("sha256").update(value).digest("hex"),
    ),
    randomUUID: () => `${String(++mockIds).padStart(8, "0")}-0000-4000-8000-000000000000`,
  };
});

jest.mock("@/lib/vendorAssets", () => ({
  vendorLibraryHash: (library: VendorLibrary) => mockHashes[library],
  readVendorLibraries: jest.fn(async (libraries: VendorLibrary[]) =>
    Object.fromEntries(libraries.map((library) => [library, mockSources[library]])),
  ),
  removeSupersededVendorCopies: jest.fn(async () => undefined),
}));

const DIR = "file:///cache/preview-pages/";
const PAGE_FILE = /^file:\/\/\/cache\/preview-pages\/mermaid-[0-9a-f]{16}\.html$/;

/** A fresh page each time: the module keeps one file per page object. */
function mermaidPage(template = "<html>{mermaid}</html>", extra: Partial<PreviewPage<"mermaid">> = {}) {
  const page: PreviewPage<"mermaid"> = {
    name: "mermaid",
    libraries: ["mermaid"],
    build: ({ mermaid }) => template.replace("{mermaid}", mermaid),
    ...extra,
  };
  return page;
}

const settle = () => new Promise((resolve) => setTimeout(resolve, 0));
const files = () => [...mockFiles.keys()].sort();

beforeEach(() => {
  mockIds = 0;
  mockFiles.clear();
  mockStorage.cacheDirectory = "file:///cache/";
  mockHashes.mermaid = "3b2f6a";
  mockSources.mermaid = "MERMAID SOURCE";
  jest.clearAllMocks();
});

describe("previewPageFile", () => {
  it("writes the page once and hands every block the same file", async () => {
    const page = mermaidPage();
    expect(readyPreviewPageFile(page)).toBeNull();
    const first = previewPageFile(page);
    const second = previewPageFile(page);
    const uri = await first;

    expect(await second).toBe(uri);
    expect(uri).toMatch(PAGE_FILE);
    expect(mockFiles.get(uri)).toBe("<html>MERMAID SOURCE</html>");
    expect(readyPreviewPageFile(page)).toBe(uri);
    expect(readVendorLibraries).toHaveBeenCalledTimes(1);
    expect(fileSystem.writeAsStringAsync).toHaveBeenCalledTimes(1);
  });

  it("writes to its own partial file beside the final name, then moves the page into place", async () => {
    const uri = await previewPageFile(mermaidPage());
    expect(fileSystem.writeAsStringAsync).toHaveBeenCalledWith(`${uri}.00000001.part`, "<html>MERMAID SOURCE</html>");
    expect(fileSystem.moveAsync).toHaveBeenCalledWith({ from: `${uri}.00000001.part`, to: uri });
    await settle();
    expect(files()).toEqual([uri]);
  });

  it("reuses the file an earlier run wrote, without reading the library", async () => {
    const uri = await previewPageFile(mermaidPage());
    jest.clearAllMocks();

    expect(await previewPageFile(mermaidPage())).toBe(uri);
    expect(readVendorLibraries).not.toHaveBeenCalled();
    expect(fileSystem.writeAsStringAsync).not.toHaveBeenCalled();
    expect(removeSupersededVendorCopies).not.toHaveBeenCalled();
  });

  it("writes again over an empty file of the same version", async () => {
    const uri = await previewPageFile(mermaidPage());
    mockFiles.set(uri, "");
    expect(await previewPageFile(mermaidPage())).toBe(uri);
    expect(mockFiles.get(uri)).toBe("<html>MERMAID SOURCE</html>");
  });

  it("versions the file by how pages embed libraries as well as by template and library", async () => {
    await previewPageFile(mermaidPage());
    // The digest covers a page-format number, so a change to how library text
    // is embedded (inlineScript) can get new files without a template change.
    expect(digestStringAsync).toHaveBeenCalledWith("SHA-256", "1\n<html>3b2f6a</html>");
  });

  it.each([
    ["the page template", () => mermaidPage("<!DOCTYPE html><html>{mermaid}</html>")],
    [
      "the library",
      () => {
        mockHashes.mermaid = "9c41d0";
        mockSources.mermaid = "MERMAID 11";
        return mermaidPage();
      },
    ],
  ])("writes a new file when %s changes and removes the old version", async (_change, next) => {
    const old = await previewPageFile(mermaidPage());
    mockFiles.set(`${DIR}chart-0123456789abcdef.html`, "chart");
    mockFiles.set(`${DIR}mermaid-fedcba9876543210.html.0badf00d.part`, "half a page");

    const uri = await previewPageFile(next());
    await settle();

    expect(uri).not.toBe(old);
    expect(files()).toEqual([`${DIR}chart-0123456789abcdef.html`, uri].sort());
    // A library was read for the new page: copies of libraries no longer shipped can go.
    expect(removeSupersededVendorCopies).toHaveBeenCalled();
  });

  it("leaves this version's other partial writes alone", async () => {
    // Another write of the same version, still in progress.
    const uri = await previewPageFile(mermaidPage());
    mockFiles.delete(uri);
    const inProgress = `${uri}.0badf00d.part`;
    mockFiles.set(inProgress, "<html>MERMAID");
    await previewPageFile(mermaidPage());
    await settle();
    expect(mockFiles.has(inProgress)).toBe(true);
  });

  it("takes the page another write put in place first", async () => {
    // Two pages of the same name and version write at once; iOS refuses the second move.
    const [a, b] = await Promise.all([previewPageFile(mermaidPage()), previewPageFile(mermaidPage())]);
    expect(b).toBe(a);
    await settle();
    expect(files()).toEqual([a]);
    expect(mockFiles.get(a)).toBe("<html>MERMAID SOURCE</html>");
  });

  it("removes the file an earlier app version kept for the page", async () => {
    mockFiles.set("file:///cache/pdf-viewer.html", "old viewer");
    mockFiles.set("file:///cache/att-1-2-doc.pdf", "%PDF");
    await previewPageFile(mermaidPage(undefined, { formerFile: "pdf-viewer.html" }));
    await settle();
    expect(mockFiles.has("file:///cache/pdf-viewer.html")).toBe(false);
    expect(mockFiles.has("file:///cache/att-1-2-doc.pdf")).toBe(true);
  });

  it("does not keep a failed write, so the next block tries again", async () => {
    const page = mermaidPage();
    jest.mocked(readVendorLibraries).mockRejectedValueOnce(new Error("asset missing"));
    await expect(previewPageFile(page)).rejects.toThrow("asset missing");
    await settle();

    expect(readyPreviewPageFile(page)).toBeNull();
    const uri = await previewPageFile(page);
    expect(mockFiles.get(uri)).toBe("<html>MERMAID SOURCE</html>");
  });

  it("writes the file again after a WebView could not load it", async () => {
    const page = mermaidPage();
    const uri = await previewPageFile(page);
    mockFiles.delete(uri);

    forgetPreviewPageFile(page, uri);
    expect(readyPreviewPageFile(page)).toBeNull();
    expect(await previewPageFile(page)).toBe(uri);
    expect(mockFiles.get(uri)).toBe("<html>MERMAID SOURCE</html>");
  });

  it("forgets only the file that failed, not a newer write", async () => {
    const page = mermaidPage();
    const uri = await previewPageFile(page);
    forgetPreviewPageFile(page, "file:///cache/preview-pages/mermaid-0000000000000000.html");
    expect(readyPreviewPageFile(page)).toBe(uri);

    forgetPreviewPageFile(page, uri);
    const rewrite = previewPageFile(page);
    // A second block reporting the same failure while the rewrite runs keeps it.
    forgetPreviewPageFile(page, uri);
    expect(previewPageFile(page)).toBe(rewrite);
  });

  it("fails without a cache directory", async () => {
    mockStorage.cacheDirectory = null;
    await expect(previewPageFile(mermaidPage())).rejects.toThrow("Storage unavailable.");
  });
});
