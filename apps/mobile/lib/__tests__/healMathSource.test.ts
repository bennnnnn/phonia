import {
  droppedOnlySlash,
  hasBareCommand,
  healDroppedCommandSlash,
  repairLeakedMath,
} from "@/lib/math/healMathSource";

describe("healDroppedCommandSlash", () => {
  it("puts the slash back on a fraction and shifts the caret", () => {
    const broken = "$frac{d^{2}}{dx^{2}}$";
    const healed = healDroppedCommandSlash(broken, broken.length, broken.length);
    expect(healed.text).toBe("$\\frac{d^{2}}{dx^{2}}$");
    expect(healed.start).toBe(broken.length + 1);
    expect(hasBareCommand(healed.text)).toBe(false);
  });

  it("leaves a real command and prose alone", () => {
    expect(healDroppedCommandSlash("$\\frac{1}{2}$").text).toBe("$\\frac{1}{2}$");
    expect(healDroppedCommandSlash("What is sqrt{81}?").text).toBe("What is sqrt{81}?");
    expect(hasBareCommand("What is sqrt{81}?")).toBe(false);
  });

  it("restores a fraction whose f was eaten and drops a leaked to", () => {
    expect(repairLeakedMath(String.raw`rac{\sqrt{8}}{2}`)).toBe(String.raw`\frac{\sqrt{8}}{2}`);
    expect(repairLeakedMath(String.raw`t o 2 \sqrt{2} = 2 \sqrt{2} o t`)).toBe(
      String.raw`2 \sqrt{2} = 2 \sqrt{2}`,
    );
    expect(repairLeakedMath(String.raw`x \to 0`)).toBe(String.raw`x \to 0`);
    const broken = "$rac{1}{2}$";
    expect(healDroppedCommandSlash(broken).text).toBe("$\\frac{1}{2}$");
  });

  it("detects a single dropped slash", () => {
    const prev = "$\\frac{d^{2}}{dx^{2}}$";
    expect(droppedOnlySlash(prev, prev.replaceAll("\\", ""))).toBe(true);
    expect(droppedOnlySlash(prev, "$\\frac{d^{2}}{dx^{}}$")).toBe(false);
  });
});
