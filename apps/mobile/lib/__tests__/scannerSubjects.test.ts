import {
  BIOLOGY_CAMERA_PROMPT,
  CHEMISTRY_CAMERA_PROMPT,
  PHYSICS_CAMERA_PROMPT,
  composerTextAfterSubjectScan,
  scannerCameraPrompt,
} from "@/lib/scanner/subjects";

describe("scanner subjects", () => {
  it("maps each subject to a distinct protocol prompt", () => {
    expect(scannerCameraPrompt("math")).toContain("math problem");
    expect(scannerCameraPrompt("physics")).toBe(PHYSICS_CAMERA_PROMPT);
    expect(scannerCameraPrompt("chemistry")).toBe(CHEMISTRY_CAMERA_PROMPT);
    expect(scannerCameraPrompt("biology")).toBe(BIOLOGY_CAMERA_PROMPT);
  });

  it("always carries the selected subject while preserving a typed caption", () => {
    expect(composerTextAfterSubjectScan("", "physics")).toBe(PHYSICS_CAMERA_PROMPT);
    expect(composerTextAfterSubjectScan("my own caption", "biology")).toBe(
      `${BIOLOGY_CAMERA_PROMPT}\n\nmy own caption`,
    );
  });
});
