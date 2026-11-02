import { MATH_CAMERA_PROMPT } from "@/lib/math/cameraPrompt";
import {
  SCAN_CONFIRMED_PREFIX,
  composerTextAfterScanConfirm,
  readsBack,
  scanSolveMessage,
} from "@/features/scanner/model/readBack";
import { PHYSICS_CAMERA_PROMPT, SCANNER_SUBJECTS } from "@/lib/scanner/subjects";

describe("readsBack", () => {
  it("reads math, physics and chemistry back; biology sends the photo", () => {
    expect(SCANNER_SUBJECTS.filter(readsBack)).toEqual(["math", "physics", "chemistry"]);
  });
});

describe("composerTextAfterScanConfirm", () => {
  it("keeps the subject's camera line when the reading is empty", () => {
    expect(composerTextAfterScanConfirm("", "math")).toBe(MATH_CAMERA_PROMPT);
    expect(composerTextAfterScanConfirm("   ", "physics")).toBe(PHYSICS_CAMERA_PROMPT);
  });

  it("appends the confirmed-reading protocol line after the subject's camera line", () => {
    expect(composerTextAfterScanConfirm("2x + 7 = 15", "math")).toBe(
      `${MATH_CAMERA_PROMPT}\n\n${SCAN_CONFIRMED_PREFIX} 2x + 7 = 15`,
    );
    expect(composerTextAfterScanConfirm(" A ball is dropped from 20 m. ", "physics")).toBe(
      `${PHYSICS_CAMERA_PROMPT}\n\n${SCAN_CONFIRMED_PREFIX} A ball is dropped from 20 m.`,
    );
  });
});

describe("composerTextAfterScanConfirm with an edited reading", () => {
  it("keeps every line of a reading but never a blank one, which ends it on the API", () => {
    expect(
      composerTextAfterScanConfirm("A ball is dropped from 80 m.\n\n  \nFind its speed.\n", "physics"),
    ).toBe(
      `${PHYSICS_CAMERA_PROMPT}\n\n${SCAN_CONFIRMED_PREFIX} A ball is dropped from 80 m.\nFind its speed.`,
    );
  });
});

describe("scanSolveMessage", () => {
  it("asks math for steps", () => {
    expect(scanSolveMessage("2x + 3 = 11", "math")).toBe("Show steps: 2x + 3 = 11");
  });

  it.each(["physics", "chemistry"] as const)("sends a %s reading as the student would type it", (subject) => {
    expect(scanSolveMessage("  Find the molar mass of H2O \n", subject)).toBe(
      "Find the molar mass of H2O",
    );
  });
});
