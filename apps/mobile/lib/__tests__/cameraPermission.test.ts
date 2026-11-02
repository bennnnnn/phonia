import { cameraPermissionNeedsSettings } from "@/lib/cameraPermission";

describe("cameraPermissionNeedsSettings", () => {
  it("is false while the OS can still show the sheet", () => {
    expect(cameraPermissionNeedsSettings(null)).toBe(false);
    expect(cameraPermissionNeedsSettings({ granted: true, canAskAgain: false })).toBe(false);
    expect(cameraPermissionNeedsSettings({ granted: false, canAskAgain: true })).toBe(false);
  });

  it("is true when camera is blocked", () => {
    expect(cameraPermissionNeedsSettings({ granted: false, canAskAgain: false })).toBe(true);
  });
});
