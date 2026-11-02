/**
 * Composer unit pad. This is a keystroke preview, not a verified solve.
 * Pint (the API registry) owns verified conversion. Each non-temperature
 * `toSi` is pinned to that registry in `test_unit_converter_pint.py`.
 * Temperature uses an offset, so it stays out of that check. Display
 * symbols and prompt tokens live here; do not generate this catalog from Pint.
 */
export const UNIT_CATEGORIES = [
  "length",
  "area",
  "volume",
  "mass",
  "temperature",
  "time",
  "speed",
  "angle",
  "force",
  "energy",
  "power",
  "pressure",
  "frequency",
  "density",
  "amount",
  "charge",
  "current",
  "voltage",
  "resistance",
  "data",
] as const;

export type UnitCategory = (typeof UNIT_CATEGORIES)[number];

type UnitDef = {
  id: string;
  symbol: string;
  name: string;
  /** Single token the model reads in `convert 5 {prompt} to {prompt}`. */
  prompt: string;
  category: UnitCategory;
  /** Multiply to reach the category SI base. Unused for temperature. */
  toSi: number;
};

function u(
  id: string,
  symbol: string,
  name: string,
  prompt: string,
  category: UnitCategory,
  toSi: number,
): UnitDef {
  return { id, symbol, name, prompt, category, toSi };
}

export const UNITS_BY_CATEGORY: Record<UnitCategory, readonly UnitDef[]> = {
  length: [
    u("angstrom", "Å", "Angstrom", "angstrom", "length", 1e-10),
    u("nm", "nm", "Nanometer", "nm", "length", 1e-9),
    u("um", "µm", "Micrometer", "µm", "length", 1e-6),
    u("mm", "mm", "Millimeter", "mm", "length", 0.001),
    u("cm", "cm", "Centimeter", "cm", "length", 0.01),
    u("m", "m", "Meter", "m", "length", 1),
    u("km", "km", "Kilometer", "km", "length", 1000),
    u("in", "in", "Inch", "in", "length", 0.0254),
    u("ft", "ft", "Foot", "ft", "length", 0.3048),
    u("yd", "yd", "Yard", "yd", "length", 0.9144),
    u("mi", "mi", "Mile", "mi", "length", 1609.344),
    u("au", "AU", "Astronomical unit", "AU", "length", 1.495978707e11),
    u("ly", "ly", "Light-year", "light-year", "length", 9.4607304725808e15),
  ],
  area: [
    u("mm2", "mm²", "Square millimeter", "mm^2", "area", 1e-6),
    u("cm2", "cm²", "Square centimeter", "cm^2", "area", 1e-4),
    u("m2", "m²", "Square meter", "m^2", "area", 1),
    u("ha", "ha", "Hectare", "ha", "area", 10000),
    u("km2", "km²", "Square kilometer", "km^2", "area", 1e6),
    u("in2", "in²", "Square inch", "in^2", "area", 0.00064516),
    u("ft2", "ft²", "Square foot", "ft^2", "area", 0.09290304),
    u("acre", "acre", "Acre", "acres", "area", 4046.8564224),
    u("mi2", "mi²", "Square mile", "mi^2", "area", 1609.344 ** 2),
  ],
  volume: [
    u("ul", "µL", "Microliter", "µL", "volume", 1e-9),
    u("ml", "mL", "Milliliter", "mL", "volume", 1e-6),
    u("cm3", "cm³", "Cubic centimeter", "cm^3", "volume", 1e-6),
    u("l", "L", "Liter", "L", "volume", 0.001),
    u("m3", "m³", "Cubic meter", "m^3", "volume", 1),
    u("tsp", "tsp", "Teaspoon", "tsp", "volume", 4.92892159375e-6),
    u("tbsp", "tbsp", "Tablespoon", "tbsp", "volume", 1.478676478125e-5),
    u("floz", "fl oz", "Fluid ounce", "fl-oz", "volume", 2.95735295625e-5),
    u("cup", "cup", "Cup", "cups", "volume", 2.365882365e-4),
    u("pt", "pt", "Pint", "pt", "volume", 16 * 2.95735295625e-5),
    u("qt", "qt", "Quart", "qt", "volume", 32 * 2.95735295625e-5),
    u("gal", "gal", "Gallon", "gal", "volume", 0.003785411784),
  ],
  mass: [
    u("ug", "µg", "Microgram", "µg", "mass", 1e-9),
    u("mg", "mg", "Milligram", "mg", "mass", 1e-6),
    u("g", "g", "Gram", "g", "mass", 0.001),
    u("kg", "kg", "Kilogram", "kg", "mass", 1),
    u("t", "t", "Tonne", "t", "mass", 1000),
    u("oz", "oz", "Ounce", "oz", "mass", 0.028349523125),
    u("lb", "lb", "Pound", "lb", "mass", 0.45359237),
    u("ton", "ton", "Ton", "ton", "mass", 2000 * 0.45359237),
  ],
  temperature: [
    u("c", "°C", "Celsius", "celsius", "temperature", 1),
    u("f", "°F", "Fahrenheit", "fahrenheit", "temperature", 1),
    u("k", "K", "Kelvin", "kelvin", "temperature", 1),
  ],
  time: [
    u("ns", "ns", "Nanosecond", "ns", "time", 1e-9),
    u("us", "µs", "Microsecond", "µs", "time", 1e-6),
    u("ms", "ms", "Millisecond", "ms", "time", 0.001),
    u("s", "s", "Second", "s", "time", 1),
    u("min", "min", "Minute", "min", "time", 60),
    u("hr", "hr", "Hour", "hr", "time", 3600),
    u("day", "day", "Day", "day", "time", 86400),
    u("week", "wk", "Week", "week", "time", 7 * 86400),
    u("yr", "yr", "Year", "year", "time", 365.25 * 86400),
  ],
  speed: [
    u("mps", "m/s", "Meter per second", "m/s", "speed", 1),
    u("kmh", "km/h", "Kilometer per hour", "km/h", "speed", 1000 / 3600),
    u("mph", "mph", "Mile per hour", "mph", "speed", 1609.344 / 3600),
    u("fps", "ft/s", "Foot per second", "ft/s", "speed", 0.3048),
    u("knot", "kn", "Knot", "knots", "speed", 1852 / 3600),
  ],
  energy: [
    u("j", "J", "Joule", "J", "energy", 1),
    u("kj", "kJ", "Kilojoule", "kJ", "energy", 1000),
    u("cal", "cal", "Calorie", "cal", "energy", 4.184),
    u("kcal", "kcal", "Kilocalorie", "kcal", "energy", 4184),
    u("wh", "Wh", "Watt-hour", "Wh", "energy", 3600),
    u("kwh", "kWh", "Kilowatt-hour", "kWh", "energy", 3.6e6),
    u("ev", "eV", "Electronvolt", "eV", "energy", 1.602176634e-19),
    u("btu", "BTU", "British thermal unit", "BTU", "energy", 1055.056),
  ],
  pressure: [
    u("pa", "Pa", "Pascal", "Pa", "pressure", 1),
    u("kpa", "kPa", "Kilopascal", "kPa", "pressure", 1000),
    u("mbar", "mbar", "Millibar", "mbar", "pressure", 100),
    u("bar", "bar", "Bar", "bar", "pressure", 1e5),
    u("atm", "atm", "Atmosphere", "atm", "pressure", 101325),
    u("torr", "Torr", "Torr", "Torr", "pressure", 101325 / 760),
    u("mmhg", "mmHg", "Millimeter of mercury", "mmHg", "pressure", 133.322387415),
    u("psi", "psi", "Pound per square inch", "psi", "pressure", 6894.757293168),
  ],
  force: [
    u("dyn", "dyn", "Dyne", "dyn", "force", 1e-5),
    u("n", "N", "Newton", "N", "force", 1),
    u("kn", "kN", "Kilonewton", "kN", "force", 1000),
    u("kgf", "kgf", "Kilogram-force", "kgf", "force", 9.80665),
    u("lbf", "lbf", "Pound-force", "lbf", "force", 4.4482216152605),
  ],
  angle: [
    u("deg", "°", "Degree", "degrees", "angle", Math.PI / 180),
    u("rad", "rad", "Radian", "radians", "angle", 1),
    u("grad", "grad", "Gradian", "grad", "angle", Math.PI / 200),
    u("arcmin", "′", "Arcminute", "arcmin", "angle", Math.PI / (180 * 60)),
    u("arcsec", "″", "Arcsecond", "arcsec", "angle", Math.PI / (180 * 3600)),
  ],
  power: [
    u("mw", "mW", "Milliwatt", "mW", "power", 0.001),
    u("w", "W", "Watt", "W", "power", 1),
    u("kw", "kW", "Kilowatt", "kW", "power", 1000),
    u("megaw", "MW", "Megawatt", "MW", "power", 1e6),
    u("hp", "hp", "Horsepower", "hp", "power", 745.6998715822702),
  ],
  frequency: [
    u("hz", "Hz", "Hertz", "Hz", "frequency", 1),
    u("khz", "kHz", "Kilohertz", "kHz", "frequency", 1e3),
    u("mhz", "MHz", "Megahertz", "MHz", "frequency", 1e6),
    u("ghz", "GHz", "Gigahertz", "GHz", "frequency", 1e9),
    u("rpm", "rpm", "Revolution per minute", "rpm", "frequency", 1 / 60),
  ],
  density: [
    u("kgm3", "kg/m³", "Kilogram per cubic meter", "kg/m^3", "density", 1),
    u("gcm3", "g/cm³", "Gram per cubic centimeter", "g/cm^3", "density", 1000),
    u("gml", "g/mL", "Gram per milliliter", "g/mL", "density", 1000),
    u("lbft3", "lb/ft³", "Pound per cubic foot", "lb/ft^3", "density", 0.45359237 / 0.3048 ** 3),
  ],
  amount: [
    u("umol", "µmol", "Micromole", "µmol", "amount", 1e-6),
    u("mmol", "mmol", "Millimole", "mmol", "amount", 0.001),
    u("mol", "mol", "Mole", "mol", "amount", 1),
  ],
  charge: [
    u("ncoulomb", "nC", "Nanocoulomb", "nC", "charge", 1e-9),
    u("ucoulomb", "µC", "Microcoulomb", "µC", "charge", 1e-6),
    u("mcoulomb", "mC", "Millicoulomb", "mC", "charge", 0.001),
    u("coulomb", "C", "Coulomb", "C", "charge", 1),
  ],
  current: [
    u("ua", "µA", "Microampere", "µA", "current", 1e-6),
    u("ma", "mA", "Milliampere", "mA", "current", 0.001),
    u("amp", "A", "Ampere", "A", "current", 1),
  ],
  voltage: [
    u("mv", "mV", "Millivolt", "mV", "voltage", 0.001),
    u("volt", "V", "Volt", "V", "voltage", 1),
    u("kv", "kV", "Kilovolt", "kV", "voltage", 1000),
  ],
  resistance: [
    u("ohm", "Ω", "Ohm", "ohm", "resistance", 1),
    u("kohm", "kΩ", "Kilohm", "kohm", "resistance", 1000),
    u("megohm", "MΩ", "Megohm", "Mohm", "resistance", 1e6),
  ],
  // kB is 1000 bytes. KiB is 1024 bytes.
  data: [
    u("byte", "B", "Byte", "B", "data", 1),
    u("kb", "kB", "Kilobyte", "kB", "data", 1000),
    u("mb", "MB", "Megabyte", "MB", "data", 1e6),
    u("gb", "GB", "Gigabyte", "GB", "data", 1e9),
    u("tb", "TB", "Terabyte", "TB", "data", 1e12),
    u("kib", "KiB", "Kibibyte", "KiB", "data", 1024),
    u("mib", "MiB", "Mebibyte", "MiB", "data", 1024 ** 2),
    u("gib", "GiB", "Gibibyte", "GiB", "data", 1024 ** 3),
  ],
};

const UNIT_BY_ID = new Map<string, UnitDef>(
  Object.values(UNITS_BY_CATEGORY).flat().map((unit) => [unit.id, unit]),
);

export function findUnit(id: string): UnitDef | undefined {
  return UNIT_BY_ID.get(id);
}

const DEFAULT_PAIRS: Record<UnitCategory, { fromId: string; toId: string }> = {
  length: { fromId: "m", toId: "cm" },
  area: { fromId: "m2", toId: "ft2" },
  volume: { fromId: "l", toId: "gal" },
  mass: { fromId: "kg", toId: "lb" },
  temperature: { fromId: "c", toId: "f" },
  time: { fromId: "s", toId: "min" },
  speed: { fromId: "kmh", toId: "mph" },
  angle: { fromId: "deg", toId: "rad" },
  force: { fromId: "n", toId: "lbf" },
  energy: { fromId: "j", toId: "kj" },
  power: { fromId: "kw", toId: "hp" },
  pressure: { fromId: "atm", toId: "psi" },
  frequency: { fromId: "hz", toId: "khz" },
  density: { fromId: "gcm3", toId: "kgm3" },
  amount: { fromId: "mol", toId: "mmol" },
  charge: { fromId: "coulomb", toId: "ucoulomb" },
  current: { fromId: "amp", toId: "ma" },
  voltage: { fromId: "volt", toId: "mv" },
  resistance: { fromId: "ohm", toId: "kohm" },
  data: { fromId: "gb", toId: "mb" },
};

export function defaultUnits(category: UnitCategory): { fromId: string; toId: string } {
  return DEFAULT_PAIRS[category];
}

function toKelvin(value: number, id: string): number {
  if (id === "c") return value + 273.15;
  if (id === "f") return ((value - 32) * 5) / 9 + 273.15;
  return value;
}

function fromKelvin(kelvin: number, id: string): number {
  if (id === "c") return kelvin - 273.15;
  if (id === "f") return ((kelvin - 273.15) * 9) / 5 + 32;
  return kelvin;
}

export function convertUnit(value: number, fromId: string, toId: string): number | null {
  const from = findUnit(fromId);
  const to = findUnit(toId);
  if (!from || !to || from.category !== to.category) return null;
  if (from.category === "temperature") {
    return fromKelvin(toKelvin(value, from.id), to.id);
  }
  return (value * from.toSi) / to.toSi;
}

export function formatConvertNumber(value: number): string {
  if (!Number.isFinite(value)) return "—";
  if (value === 0) return "0";
  const abs = Math.abs(value);
  if (abs >= 1e10 || (abs < 1e-6 && abs > 0)) {
    return value.toExponential(4).replace(/(\.\d*?)0+e/, "$1e").replace(/\.e/, "e");
  }
  return String(Number(value.toPrecision(8)));
}

export const CONVERTER_DEFAULT_DIGITS = "1";

export function appendConverterDigit(
  current: string,
  key: string,
  fresh = false,
): string {
  if (key === "AC") return CONVERTER_DEFAULT_DIGITS;
  if (key === "back") {
    if (current.length <= 1 || current === "-0" || (current.startsWith("-") && current.length === 2)) {
      return CONVERTER_DEFAULT_DIGITS;
    }
    return current.slice(0, -1);
  }
  if (key === "±") {
    if (current === "0" || current === "0.") return current;
    return current.startsWith("-") ? current.slice(1) : `-${current}`;
  }
  if (fresh && /^\d$/.test(key)) return key;
  if (fresh && key === ".") return "0.";
  if (key === ".") {
    if (current.includes(".")) return current;
    return `${current}.`;
  }
  if (!/^\d$/.test(key)) return current;
  if (current === "0") return key;
  if (current === "-0") return `-${key}`;
  if (current.replace("-", "").replace(".", "").length >= 12) return current;
  return current + key;
}

/** Prompt sent when the user taps Ask on the converter pad. */
export function converterAskText(digits: string, fromPrompt: string, toPrompt: string): string {
  const left = digits.endsWith(".") ? digits.slice(0, -1) : digits;
  return `convert ${left} ${fromPrompt} to ${toPrompt}`;
}
