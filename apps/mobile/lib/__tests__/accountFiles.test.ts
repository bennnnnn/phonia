import { deleteAsync, getInfoAsync, readDirectoryAsync } from "expo-file-system/legacy";

import { deleteAccountFiles, namedPdfFile, sweepOldPickerCopies } from "@/lib/accountFiles";

jest.mock("expo-file-system/legacy", () => ({
  cacheDirectory: "file:///cache/",
  deleteAsync: jest.fn(async () => undefined),
  getInfoAsync: jest.fn(),
  readDirectoryAsync: jest.fn(async () => []),
}));

const listing: Record<string, string[]> = {
  "file:///cache/": ["recall-export-1.json", "other.txt"],
  "file:///cache/Print/": ["3F2A.pdf", "Spanish verbs.pdf", "Café #2.pdf", "notes.txt"],
  "file:///cache/ExpoAudio/": ["recording-1.m4a"],
  "file:///cache/ImagePicker/": ["A1.jpg"],
  "file:///cache/DocumentPicker/": ["B2.pdf"],
  "file:///cache/ImageManipulator/": ["C3.jpg"],
};

const DAY_MS = 24 * 60 * 60 * 1000;
const NOW = Date.UTC(2026, 9, 23);
/** Days since each picker copy was written. */
const ageDays: Record<string, number> = {
  "file:///cache/ImagePicker/A1.jpg": 8,
  "file:///cache/DocumentPicker/B2.pdf": 2,
  "file:///cache/ImageManipulator/C3.jpg": 30,
};

beforeEach(() => {
  jest.clearAllMocks();
  jest.mocked(readDirectoryAsync).mockImplementation(async (dir) => listing[dir] ?? []);
  jest.mocked(getInfoAsync).mockImplementation(async (uri) => ({
    exists: true,
    uri,
    size: 1,
    isDirectory: false,
    // Legacy file info reports seconds.
    modificationTime: (NOW - (ageDays[uri] ?? 0) * DAY_MS) / 1000,
  }));
});

it("names a PDF with a URI iOS accepts", () => {
  expect(namedPdfFile("Spanish verbs.pdf")).toBe("file:///cache/Print/Spanish%20verbs.pdf");
});

it("sign-out deletes a named PDF by the URI it was written under", async () => {
  await deleteAccountFiles();
  const deleted = jest.mocked(deleteAsync).mock.calls.map(([uri]) => uri);
  expect(deleted.sort()).toEqual(
    [
      "file:///cache/recall-export-1.json",
      "file:///cache/Print/3F2A.pdf",
      namedPdfFile("Spanish verbs.pdf"),
      namedPdfFile("Café #2.pdf"),
      "file:///cache/ExpoAudio/recording-1.m4a",
      // Every photo and file the person picked or cropped.
      "file:///cache/ImagePicker/A1.jpg",
      "file:///cache/DocumentPicker/B2.pdf",
      "file:///cache/ImageManipulator/C3.jpg",
    ].sort(),
  );
});

it("the launch sweep deletes only picker copies older than a week", async () => {
  await sweepOldPickerCopies(NOW);
  const deleted = jest.mocked(deleteAsync).mock.calls.map(([uri]) => uri);
  expect(deleted.sort()).toEqual(
    ["file:///cache/ImagePicker/A1.jpg", "file:///cache/ImageManipulator/C3.jpg"].sort(),
  );
});
