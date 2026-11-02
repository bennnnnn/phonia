import {
  DOCUMENT_MIME_TYPES,
  MAX_ATTACHMENT_BYTES,
  UPLOADABLE_IMAGE_TYPES,
} from "@/features/attachments/model/attachmentLimits";

// The lib test project has Jest types but no Node types (see katexParity.test.ts).
declare const __dirname: string;
const { readFileSync } = jest.requireActual<{
  readFileSync(path: string, encoding: "utf8"): string;
}>("node:fs");
const { join } = jest.requireActual<{ join(...parts: string[]): string }>("node:path");

// The phone refuses a file before Send with the same rules the API applies at
// presign. These read the API's own sources so the two cannot drift apart.
const API = join(__dirname, "../../../../../api/app");
const read = (path: string) => readFileSync(join(API, path), "utf8");

function frozenset(source: string, name: string): Set<string> {
  const block = source.match(new RegExp(`${name} = frozenset\\(\\s*\\{([\\s\\S]*?)\\}\\s*\\)`))?.[1] ?? "";
  return new Set([...block.matchAll(/"([^"]+)"/g)].map((match) => match[1]));
}

it("caps a file at the API's MAX_ATTACHMENT_SIZE", () => {
  const expression = read("core/attachment_limits.py").match(/MAX_ATTACHMENT_SIZE = ([\d\s*_]+)/)?.[1] ?? "";
  const bytes = expression.split("*").reduce((product: number, factor: string) => product * Number(factor.replace(/_/g, "")), 1);
  expect(bytes).toBe(MAX_ATTACHMENT_BYTES);
  // Presign checks the same constant, not a second copy of the number.
  expect(read("modules/attachments/schemas.py")).toContain("le=MAX_ATTACHMENT_SIZE");
});

it("sends as-is exactly the image types the API stores, aliases aside", () => {
  const api = frozenset(read("modules/attachments/content_types.py"), "IMAGE_CONTENT_TYPES");
  api.delete("image/jpg");
  expect([...UPLOADABLE_IMAGE_TYPES].sort()).toEqual([...api].sort());
});

it("offers exactly the document types the API accepts", () => {
  const api = frozenset(read("modules/attachments/content_types.py"), "DOCUMENT_CONTENT_TYPES");
  expect([...DOCUMENT_MIME_TYPES].sort()).toEqual([...api].sort());
});
