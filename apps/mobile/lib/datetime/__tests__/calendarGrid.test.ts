import {
  addMonths,
  clampDay,
  compareDays,
  daysInMonth,
  dayOutOfRange,
  firstDayOfWeek,
  monthGrid,
  monthInRange,
  monthYearLabel,
  weekdayLabels,
  withDay,
  yearRange,
} from "@/lib/datetime/calendarGrid";
import { refreshPhoneClock } from "@/lib/datetime/format";
import type { Weekday } from "@/lib/datetime/phoneClock";
import { ensureLocale } from "@/lib/i18n";

/** The phone's First Day of Week; undefined: a build that cannot read it. */
let mockWeekStart: Weekday | undefined;
jest.mock("@/lib/datetime/phoneClock", () => {
  const actual = jest.requireActual<typeof import("@/lib/datetime/phoneClock")>("@/lib/datetime/phoneClock");
  return { ...actual, readPhoneClock: () => ({ ...actual.readPhoneClock(), weekStart: mockWeekStart }) };
});

function setPhoneWeekStart(weekStart: Weekday | undefined): void {
  mockWeekStart = weekStart;
  refreshPhoneClock();
}

describe("daysInMonth", () => {
  it.each([
    [2024, 1, 29],
    [2023, 1, 28],
    [2000, 1, 29],
    [1900, 1, 28],
    [2026, 8, 30],
    [2026, 11, 31],
  ])("%i-%i has %i days", (year, month, days) => {
    expect(daysInMonth(year, month)).toBe(days);
  });
});

describe("monthGrid", () => {
  // September 2026 starts on a Tuesday.
  it("starts a Sunday-first week with two blanks", () => {
    const weeks = monthGrid(2026, 8, 0);
    expect(weeks).toHaveLength(6);
    expect(weeks[0]).toEqual([null, null, 1, 2, 3, 4, 5]);
    expect(weeks[4]).toEqual([27, 28, 29, 30, null, null, null]);
  });

  it("starts a Monday-first week with one blank", () => {
    const weeks = monthGrid(2026, 8, 1);
    expect(weeks[0]).toEqual([null, 1, 2, 3, 4, 5, 6]);
  });

  it("starts a Saturday-first week with three blanks", () => {
    expect(monthGrid(2026, 8, 6)[0]).toEqual([null, null, null, 1, 2, 3, 4]);
  });

  it("always lists every day exactly once in six weeks", () => {
    for (const [year, month] of [[2024, 1], [2026, 1], [2026, 7], [2027, 4]]) {
      for (const start of [0, 1, 6] as const) {
        const days = monthGrid(year, month, start).flat().filter((day) => day != null);
        expect(days).toEqual(Array.from({ length: daysInMonth(year, month) }, (_, i) => i + 1));
      }
    }
  });
});

describe("month and day arithmetic", () => {
  it("moves across year boundaries", () => {
    expect(addMonths({ year: 2026, month: 11 }, 1)).toEqual({ year: 2027, month: 0 });
    expect(addMonths({ year: 2026, month: 0 }, -1)).toEqual({ year: 2025, month: 11 });
    expect(addMonths({ year: 2026, month: 5 }, -18)).toEqual({ year: 2024, month: 11 });
  });

  it("compares calendar days and ignores the time", () => {
    expect(compareDays(new Date(2026, 8, 26, 23), new Date(2026, 8, 26, 1))).toBe(0);
    expect(compareDays(new Date(2026, 8, 25), new Date(2026, 8, 26))).toBeLessThan(0);
    expect(compareDays(new Date(2027, 0, 1), new Date(2026, 11, 31))).toBeGreaterThan(0);
  });

  it("keeps the time when picking a day", () => {
    const date = new Date(2026, 0, 31, 9, 30);
    const picked = withDay(date, { year: 2026, month: 8 }, 26);
    expect([picked.getMonth(), picked.getDate(), picked.getHours()]).toEqual([8, 26, 9]);
  });
});

describe("limits", () => {
  const min = new Date(2026, 8, 10);
  const max = new Date(2026, 10, 5);

  it("marks days outside min and max", () => {
    expect(dayOutOfRange(new Date(2026, 8, 9, 23), min, max)).toBe(true);
    expect(dayOutOfRange(new Date(2026, 8, 10, 0), min, max)).toBe(false);
    expect(dayOutOfRange(new Date(2026, 10, 5, 23), min, max)).toBe(false);
    expect(dayOutOfRange(new Date(2026, 10, 6), min, max)).toBe(true);
    expect(dayOutOfRange(new Date(1990, 0, 1))).toBe(false);
  });

  it("allows a month when any of its days can be picked", () => {
    expect(monthInRange({ year: 2026, month: 7 }, min, max)).toBe(false);
    expect(monthInRange({ year: 2026, month: 8 }, min, max)).toBe(true);
    expect(monthInRange({ year: 2026, month: 10 }, min, max)).toBe(true);
    expect(monthInRange({ year: 2026, month: 11 }, min, max)).toBe(false);
  });

  it("clamps to the nearest allowed day and keeps the time", () => {
    const early = clampDay(new Date(2026, 0, 1, 7, 45), min, max);
    expect([early.getMonth(), early.getDate(), early.getHours(), early.getMinutes()]).toEqual([8, 10, 7, 45]);
    const late = clampDay(new Date(2027, 0, 1), min, max);
    expect([late.getMonth(), late.getDate()]).toEqual([10, 5]);
  });

  it("lists years inside the limits and always the selected one", () => {
    const now = new Date(2026, 8, 26);
    expect(yearRange(2026, min, max, now)).toEqual([2026]);
    const open = yearRange(2026, null, null, now);
    expect(open[0]).toBe(1926);
    expect(open.at(-1)).toBe(2076);
    expect(yearRange(1900, null, null, now)[0]).toBe(1900);
  });
});

describe("locale week", () => {
  it.each([
    ["en-US", 0],
    ["en-GB", 1],
    ["de-DE", 1],
    ["pt-BR", 0],
    ["am-ET", 0],
    ["ar-EG", 6],
    ["en", 0],
    ["fr", 1],
    ["ru", 1],
  ])("%s starts the week on day %i", (locale, day) => {
    expect(firstDayOfWeek(locale)).toBe(day);
  });

  afterEach(() => ensureLocale("en"));

  describe("the phone's own setting", () => {
    afterEach(() => setPhoneWeekStart(undefined));

    it.each([[1], [6], [0]] as const)("starts the device's week on the phone's First Day of Week, %i", (day) => {
      setPhoneWeekStart(day);
      expect(firstDayOfWeek()).toBe(day);
    });

    it("leaves a locale asked for by name to its region", () => {
      setPhoneWeekStart(1);
      expect(firstDayOfWeek("en-US")).toBe(0);
      expect(firstDayOfWeek("ar-EG")).toBe(6);
    });

    it("works the device's week out from its locale when the phone cannot say", () => {
      setPhoneWeekStart(undefined);
      expect(firstDayOfWeek()).toBe(firstDayOfWeek(new Intl.DateTimeFormat().resolvedOptions().locale));
    });
  });

  it("labels weekday columns from the week start, in the app's language", async () => {
    const labels = weekdayLabels(1);
    expect(labels.map((label) => label.narrow)).toEqual(["M", "T", "W", "T", "F", "S", "S"]);
    expect(labels[0].long).toBe("Monday");
    expect(weekdayLabels(0)[0].long).toBe("Sunday");
    await ensureLocale("de");
    expect(weekdayLabels(1)[0].long).toBe("Montag");
  });

  it("names the month and year in the app's language", async () => {
    expect(monthYearLabel({ year: 2026, month: 8 })).toBe("September 2026");
    await ensureLocale("es");
    expect(monthYearLabel({ year: 2026, month: 8 })).toBe("septiembre de 2026");
  });
});
