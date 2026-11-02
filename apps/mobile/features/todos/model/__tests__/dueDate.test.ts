import { describeDueAt, toDueAtIso } from "@/features/todos/model/dueDate";
import { refreshPhoneClock } from "@/lib/datetime/format";
import type { PhoneClock } from "@/lib/datetime/phoneClock";
import { ensureLocale } from "@/lib/i18n";

// The engine's zone (the one the day math reads); the hour cycle is the phone's switch.
let mockPhone: PhoneClock = { timeZone: undefined, hourCycle: "h12" };
jest.mock("@/lib/datetime/phoneClock", () => ({ readPhoneClock: () => mockPhone }));

describe("describeDueAt", () => {
  afterEach(() => {
    jest.useRealTimers();
  });

  function freezeAt(local: Date) {
    jest.useFakeTimers();
    jest.setSystemTime(local);
  }

  it("returns null for missing or invalid values", () => {
    expect(describeDueAt(null)).toBeNull();
    expect(describeDueAt("not-a-date")).toBeNull();
  });

  it("labels an overdue time later the same day", () => {
    freezeAt(new Date(2026, 8, 8, 15, 0, 0));
    const iso = toDueAtIso(new Date(2026, 8, 8, 9, 0, 0));
    expect(describeDueAt(iso)).toEqual({
      label: "Overdue today",
      tone: "overdue",
    });
  });

  it("labels overdue by day count", () => {
    freezeAt(new Date(2026, 8, 8, 12, 0, 0));
    const iso = toDueAtIso(new Date(2026, 8, 5, 9, 0, 0));
    expect(describeDueAt(iso)).toEqual({
      label: "3d overdue",
      tone: "overdue",
    });
  });

  it.each([
    ["en", "h12", "Today 5:30 PM"],
    ["en", "h23", "Today 17:30"],
    ["de", "h12", "Heute 5:30 PM"],
    ["de", "h23", "Heute 17:30"],
  ] as const)("labels a later time today in %s on a %s phone", async (language, hourCycle, label) => {
    mockPhone = { timeZone: undefined, hourCycle };
    refreshPhoneClock();
    await ensureLocale(language);
    try {
      freezeAt(new Date(2026, 8, 8, 9, 0, 0));
      const result = describeDueAt(toDueAtIso(new Date(2026, 8, 8, 17, 30, 0)));
      expect({ ...result, label: result?.label.replace(/\s/g, " ") }).toEqual({ label, tone: "today" });
    } finally {
      await ensureLocale("en");
    }
  });

  it("writes a date later this week and later on in the app's language", async () => {
    await ensureLocale("de");
    try {
      freezeAt(new Date(2026, 8, 8, 12, 0, 0));
      expect(describeDueAt(toDueAtIso(new Date(2026, 8, 11, 10, 0, 0)))?.label).toBe("Fr., 11. Sept.");
      expect(describeDueAt(toDueAtIso(new Date(2026, 9, 20, 10, 0, 0)))?.label).toBe("20. Okt. 2026");
    } finally {
      await ensureLocale("en");
    }
  });

  it("labels tomorrow", () => {
    freezeAt(new Date(2026, 8, 8, 12, 0, 0));
    const iso = toDueAtIso(new Date(2026, 8, 9, 10, 0, 0));
    expect(describeDueAt(iso)).toEqual({
      label: "Tomorrow",
      tone: "soon",
    });
  });
});
