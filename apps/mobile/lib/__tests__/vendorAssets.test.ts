import { Asset } from "expo-asset";
import { readAsStringAsync } from "expo-file-system/legacy";

import {
  readVendorLibraries,
  readVendorLibrary,
  removeSupersededVendorCopies,
  vendorLibraryHash,
  type VendorLibrary,
} from "@/lib/vendorAssets";

/** In this project a required .txt asset is `{ testUri: "<path>" }`; Metro gives a number. */
type TestAsset = { testUri: string };

/** Files on the device: uri → contents. */
const mockFiles = new Map<string, string>();
const mockAssets = new Map<string, MockAssetShape>();
const mockState = { hash: "0f3c9a" as string | null, downloads: [] as string[], copiesTo: "file:///cache/" };

type MockAssetShape = { hash: string | null; localUri: string | null; downloaded: boolean; downloadAsync(): Promise<unknown> };

jest.mock("expo-asset", () => ({
  Asset: {
    // Like Expo Go: one Asset per asset, which remembers it was downloaded.
    fromModule: jest.fn((module: TestAsset) => {
      let asset = mockAssets.get(module.testUri);
      if (!asset) {
        const created: MockAssetShape = {
          hash: mockState.hash,
          localUri: null,
          downloaded: false,
          async downloadAsync() {
            if (created.downloaded) return created;
            // A copy in the cache directory, as Metro downloads and Android's raw resources make.
            const name = module.testUri.split("/").pop() ?? "";
            created.localUri = `${mockState.copiesTo}ExponentAsset-${created.hash}-${name}`;
            mockFiles.set(created.localUri, `source of ${name}`);
            mockState.downloads.push(name);
            created.downloaded = true;
            return created;
          },
        };
        asset = created;
        mockAssets.set(module.testUri, asset);
      }
      return asset;
    }),
  },
}));

jest.mock("expo-file-system/legacy", () => ({
  cacheDirectory: "file:///cache/",
  getInfoAsync: jest.fn(async (uri: string) => ({ exists: mockFiles.has(uri), uri })),
  readAsStringAsync: jest.fn(async (uri: string) => {
    const contents = mockFiles.get(uri);
    if (contents === undefined) throw new Error(`${uri} is missing`);
    return contents;
  }),
  readDirectoryAsync: jest.fn(async (dir: string) =>
    [...mockFiles.keys()].filter((uri) => uri.startsWith(dir)).map((uri) => uri.slice(dir.length)),
  ),
  deleteAsync: jest.fn(async (uri: string) => {
    mockFiles.delete(uri);
  }),
}));

/** The file each library's asset module was required from. */
function assetFile(library: VendorLibrary): string {
  vendorLibraryHash(library);
  const module = jest.mocked(Asset.fromModule).mock.calls.at(-1)?.[0] as unknown as TestAsset;
  return module.testUri.split("/").pop() ?? "";
}

beforeEach(() => {
  mockFiles.clear();
  mockAssets.clear();
  mockState.hash = "0f3c9a";
  mockState.downloads = [];
  jest.clearAllMocks();
});

describe("vendored library assets", () => {
  it.each([
    ["katexCss", "katex.min.css.txt"],
    ["mermaid", "mermaid.min.js.txt"],
    ["pdf", "pdf.min.js.txt"],
    ["pdfWorker", "pdf.worker.min.js.txt"],
    ["smilesDrawer", "smiles-drawer.min.js.txt"],
    ["vega", "vega.min.js.txt"],
    ["vegaEmbed", "vega-embed.min.js.txt"],
    ["vegaLite", "vega-lite.min.js.txt"],
  ] as const)("ships %s as lib/vendor/%s", (library, file) => {
    expect(assetFile(library)).toBe(file);
  });

  it("knows a library's content hash without reading it", () => {
    expect(vendorLibraryHash("mermaid")).toBe("0f3c9a");
    expect(mockState.downloads).toEqual([]);
    expect(readAsStringAsync).not.toHaveBeenCalled();
  });

  it("refuses a library with no content hash", () => {
    mockState.hash = null;
    expect(() => vendorLibraryHash("mermaid")).toThrow("no content hash");
  });

  it("reads a library from its file on the device", async () => {
    await expect(readVendorLibrary("katexCss")).resolves.toBe("source of katex.min.css.txt");
    expect(mockState.downloads).toEqual(["katex.min.css.txt"]);
  });

  it("downloads again a copy that was cleared since this run made it", async () => {
    await readVendorLibrary("mermaid");
    mockFiles.clear();
    await expect(readVendorLibrary("mermaid")).resolves.toBe("source of mermaid.min.js.txt");
    expect(mockState.downloads).toEqual(["mermaid.min.js.txt", "mermaid.min.js.txt"]);
  });

  it("fails when the asset never reached the device", async () => {
    jest.mocked(Asset.fromModule).mockReturnValueOnce({
      hash: "0f3c9a",
      localUri: null,
      downloadAsync: async () => undefined,
    } as unknown as Asset);
    await expect(readVendorLibrary("mermaid")).rejects.toThrow("not on the device");
  });

  it("reads several libraries by name", async () => {
    await expect(readVendorLibraries(["pdf", "pdfWorker"])).resolves.toEqual({
      pdf: "source of pdf.min.js.txt",
      pdfWorker: "source of pdf.worker.min.js.txt",
    });
  });
});

describe("removeSupersededVendorCopies", () => {
  it("removes cached copies of libraries this build no longer ships, and nothing else", async () => {
    mockState.hash = "aaaa1111";
    const keep = [
      "file:///cache/ExponentAsset-aaaa1111.txt",
      "file:///cache/ExponentAsset-bbbb2222.png",
      "file:///cache/att-1-2-doc.pdf",
      "file:///cache/preview-pages/mermaid-0123456789abcdef.html",
    ];
    for (const uri of [...keep, "file:///cache/ExponentAsset-cccc3333.txt"]) mockFiles.set(uri, "x");

    await removeSupersededVendorCopies();
    expect([...mockFiles.keys()].sort()).toEqual(keep.sort());
  });
});
