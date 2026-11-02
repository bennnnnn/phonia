import { deleteAsync, getInfoAsync, readDirectoryAsync } from "expo-file-system/legacy";

import {
  ATTACHMENT_FILE_MAX_AGE_MS,
  ATTACHMENT_FILES_MAX_BYTES,
  sweepAttachmentFiles,
} from "@/features/attachments/model/attachmentFileStore";

const mockDisk = new Map<string, { size: number; mtime: number; dir?: boolean }>();

jest.mock("expo-file-system/legacy", () => ({
  cacheDirectory: "file:///cache/",
  getInfoAsync: jest.fn(),
  readDirectoryAsync: jest.fn(),
  deleteAsync: jest.fn(),
}));
jest.mock("expo-crypto", () => ({ CryptoDigestAlgorithm: { SHA256: "SHA-256" }, digestStringAsync: jest.fn() }));
jest.mock("@/lib/config", () => ({ getApiUrl: () => "https://api.test" }));

const NOW = Date.UTC(2026, 9, 19);
const MB = 1024 * 1024;

function put(name: string, ageMs: number, size = MB, dir = false) {
  mockDisk.set(`file:///cache/${name}`, { size, mtime: (NOW - ageMs) / 1000, dir });
}
const left = () => [...mockDisk.keys()].map((path) => path.slice("file:///cache/".length)).sort();

beforeEach(() => {
  mockDisk.clear();
  jest.mocked(readDirectoryAsync).mockImplementation(async () => left());
  jest.mocked(getInfoAsync).mockImplementation(async (path: string) => {
    const file = mockDisk.get(path);
    return file
      ? { exists: true, isDirectory: Boolean(file.dir), uri: path, size: file.size, modificationTime: file.mtime }
      : { exists: false, isDirectory: false, uri: path };
  });
  jest.mocked(deleteAsync).mockImplementation(async (path: string) => { mockDisk.delete(path); });
});

it("removes copies past the age limit and keeps recent ones", async () => {
  put("att-old.pdf", ATTACHMENT_FILE_MAX_AGE_MS + 60_000);
  put("att-new.pdf", 60_000);
  await sweepAttachmentFiles(() => false, NOW);
  expect(left()).toEqual(["att-new.pdf"]);
});

it("removes the oldest copies until the rest fit the byte budget", async () => {
  const half = ATTACHMENT_FILES_MAX_BYTES / 2;
  put("att-a.pdf", 3_000, half);
  put("att-b.pdf", 2_000, half);
  put("att-c.pdf", 1_000, half);
  await sweepAttachmentFiles(() => false, NOW);
  expect(left()).toEqual(["att-b.pdf", "att-c.pdf"]);
});

it("removes a partial download a closed run left, but never a file in use", async () => {
  put("att-x.pdf.abc.part", 1_000);
  put("att-y.pdf.def.part", 1_000);
  put("att-z.pdf", ATTACHMENT_FILE_MAX_AGE_MS * 2);
  await sweepAttachmentFiles((path) => path.endsWith("att-y.pdf.def.part") || path.endsWith("att-z.pdf"), NOW);
  expect(left()).toEqual(["att-y.pdf.def.part", "att-z.pdf"]);
});

it("leaves other cache owners and directories alone", async () => {
  put("cached-user.json", ATTACHMENT_FILE_MAX_AGE_MS * 2);
  put("pdf-viewer.html", ATTACHMENT_FILE_MAX_AGE_MS * 2);
  put("att-folder", ATTACHMENT_FILE_MAX_AGE_MS * 2, 0, true);
  await sweepAttachmentFiles(() => false, NOW);
  expect(left()).toEqual(["att-folder", "cached-user.json", "pdf-viewer.html"]);
});
