import {
  appendConverterDigit,
  convertUnit,
  converterAskText,
  defaultUnits,
  findUnit,
  formatConvertNumber,
  UNIT_CATEGORIES,
  UNITS_BY_CATEGORY,
} from "@/features/chat/model/unitConverter";

describe("convertUnit", () => {
  it("converts length through meters", () => {
    expect(convertUnit(1, "m", "cm")).toBe(100);
    expect(convertUnit(5, "m", "cm")).toBe(500);
  });

  it("converts temperature", () => {
    expect(convertUnit(0, "c", "f")).toBeCloseTo(32);
  });

  it("converts speed, energy, pressure, force, and angle", () => {
    expect(convertUnit(100, "kmh", "mph")).toBeCloseTo(62.137, 2);
    expect(convertUnit(1000, "j", "kj")).toBe(1);
    expect(convertUnit(1, "atm", "pa")).toBe(101325);
    expect(convertUnit(1, "kn", "n")).toBe(1000);
    expect(convertUnit(180, "deg", "rad")).toBeCloseTo(Math.PI);
  });

  it("converts school and everyday units", () => {
    expect(convertUnit(1, "m", "nm")).toBeCloseTo(1e9);
    expect(convertUnit(1, "cm3", "ml")).toBe(1);
    expect(convertUnit(1, "t", "kg")).toBe(1000);
    expect(convertUnit(1, "day", "hr")).toBe(24);
    expect(convertUnit(1, "hp", "w")).toBeCloseTo(745.7, 0);
    expect(convertUnit(60, "rpm", "hz")).toBeCloseTo(1);
    expect(convertUnit(1, "gcm3", "kgm3")).toBe(1000);
    expect(convertUnit(1, "gb", "mb")).toBe(1000);
    expect(convertUnit(1, "gib", "mib")).toBe(1024);
    expect(convertUnit(1, "kohm", "ohm")).toBe(1000);
    expect(convertUnit(180, "deg", "grad")).toBeCloseTo(200);
  });

  it("converts the default pair in every category", () => {
    for (const category of UNIT_CATEGORIES) {
      const { fromId, toId } = defaultUnits(category);
      expect(fromId).not.toBe(toId);
      expect(findUnit(fromId)?.category).toBe(category);
      expect(findUnit(toId)?.category).toBe(category);
      expect(convertUnit(1, fromId, toId)).not.toBeNull();
    }
  });

  it("keeps every unit id unique", () => {
    const ids = Object.values(UNITS_BY_CATEGORY).flat().map((unit) => unit.id);
    expect(new Set(ids).size).toBe(ids.length);
    expect(findUnit("knot")?.category).toBe("speed");
    expect(findUnit("kn")?.category).toBe("force");
  });
});

describe("appendConverterDigit", () => {
  it("replaces a leading zero", () => {
    expect(appendConverterDigit("0", "5")).toBe("5");
  });

  it("clears and backspaces to 1, not 0", () => {
    expect(appendConverterDigit("12", "AC")).toBe("1");
    expect(appendConverterDigit("12", "back")).toBe("1");
    expect(appendConverterDigit("1", "back")).toBe("1");
  });

  it("replaces the starting 1 on the first digit", () => {
    expect(appendConverterDigit("1", "5", true)).toBe("5");
    expect(appendConverterDigit("1", "2", false)).toBe("12");
  });

  it("toggles sign and allows one decimal", () => {
    expect(appendConverterDigit("5", "±")).toBe("-5");
    expect(appendConverterDigit("5", ".")).toBe("5.");
    expect(appendConverterDigit("5.", ".")).toBe("5.");
  });
});

describe("converterAskText", () => {
  it("asks the model to convert — does not include an answer", () => {
    expect(converterAskText("5", "m", "cm")).toBe("convert 5 m to cm");
    expect(converterAskText("5", "m", "cm")).not.toContain("=");
  });

  it("defaults length to meters → centimeters", () => {
    expect(defaultUnits("length")).toEqual({ fromId: "m", toId: "cm" });
    expect(defaultUnits("speed")).toEqual({ fromId: "kmh", toId: "mph" });
    expect(defaultUnits("energy")).toEqual({ fromId: "j", toId: "kj" });
  });

  it("formats the live result without float noise", () => {
    expect(formatConvertNumber(100)).toBe("100");
  });
});
