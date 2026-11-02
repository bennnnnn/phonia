import { hasUsefulScannerText } from "@/features/scanner/model/liveText";

describe("live scanner text", () => {
  it("treats a formula as ready even when it has no digit", () => {
    expect(hasUsefulScannerText("NaCl")).toBe(true);
    expect(hasUsefulScannerText("H2O")).toBe(true);
    expect(hasUsefulScannerText("CO2")).toBe(true);
  });

  it("still ignores a short ordinary word", () => {
    expect(hasUsefulScannerText("OK")).toBe(false);
    expect(hasUsefulScannerText("Hi")).toBe(false);
    expect(hasUsefulScannerText("water")).toBe(false);
  });
});
