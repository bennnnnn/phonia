/**
 * The phone's half of docs/fixtures/scanner_prompts.json (code-health audit CLAR-13):
 * the API recognizes a scan by its exact caption, so both sides compare their constants
 * with the one fixture.
 */
import fixture from "../../../../docs/fixtures/scanner_prompts.json";
import { SCAN_CONFIRMED_PREFIX } from "@/features/scanner/model/readBack";
import { SCANNER_CAMERA_PROMPTS } from "@/lib/scanner/subjects";

describe("scan captions", () => {
  it("are the fixture's, letter for letter", () => {
    expect(SCANNER_CAMERA_PROMPTS).toEqual(fixture.camera_prompts);
    expect(SCAN_CONFIRMED_PREFIX).toBe(fixture.confirmed_prefix);
  });
});
