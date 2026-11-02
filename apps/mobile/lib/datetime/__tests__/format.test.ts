import type { PhoneClock } from "@/lib/datetime/phoneClock";
import {
  DATE_FORMAT_CHANGED,
  formatCalendarDay,
  formatDate,
  formatMinuteOfDay,
  formatTimeZoneName,
  refreshPhoneClock,
  userUses24HourClock,
  userWeekStart,
  wallClock,
} from "@/lib/datetime/format";
import i18n, { ensureLocale } from "@/lib/i18n";

let mockPhone: PhoneClock = { timeZone: "UTC", hourCycle: "h12" };
jest.mock("@/lib/datetime/phoneClock", () => ({ readPhoneClock: () => mockPhone }));

/** ICU puts a narrow no-break space before AM/PM; compare words, not spacing. */
const plain = (text: string) => text.replace(/\s/g, " ");

async function setClock(phone: PhoneClock, language = "en"): Promise<void> {
  mockPhone = phone;
  refreshPhoneClock();
  await ensureLocale(language);
}

afterEach(async () => {
  await setClock({ timeZone: "UTC", hourCycle: "h12" });
  jest.restoreAllMocks();
});

// 23:30 UTC: still Oct 25 in UTC and New York, already Oct 26 in Kathmandu (+5:45)
// and Kiritimati (+14). Each zone, each hour cycle, two languages.
describe("the user's zone, the phone's hour cycle, the app's language", () => {
  const at = new Date(Date.UTC(2026, 9, 25, 23, 30));

  it.each([
    ["en", "UTC", "Sun, Oct 25", "11:30 PM", "23:30"],
    ["en", "America/New_York", "Sun, Oct 25", "7:30 PM", "19:30"],
    ["en", "Asia/Kathmandu", "Mon, Oct 26", "5:15 AM", "05:15"],
    ["en", "Pacific/Kiritimati", "Mon, Oct 26", "1:30 PM", "13:30"],
    ["de", "UTC", "So., 25. Okt.", "11:30 PM", "23:30"],
    ["de", "America/New_York", "So., 25. Okt.", "7:30 PM", "19:30"],
    ["de", "Asia/Kathmandu", "Mo., 26. Okt.", "5:15 AM", "5:15"],
    ["de", "Pacific/Kiritimati", "Mo., 26. Okt.", "1:30 PM", "13:30"],
  ])("%s in %s: %s, %s on a 12-hour phone, %s on a 24-hour one", async (language, zone, day, twelve, twentyFour) => {
    await setClock({ timeZone: zone, hourCycle: "h12" }, language);
    expect(formatDate(at, "weekdayDate")).toBe(day);
    expect(plain(formatDate(at, "time"))).toBe(twelve);
    await setClock({ timeZone: zone, hourCycle: "h23" }, language);
    expect(formatDate(at, "weekdayDate")).toBe(day);
    expect(formatDate(at, "time")).toBe(twentyFour);
  });

  it("writes the phone's hour cycle even where the language's default is the other one", async () => {
    // English defaults to 12 hours and German to 24; the phone's switch wins in both.
    await setClock({ timeZone: "UTC", hourCycle: "h23" }, "en");
    expect(formatDate(at, "time")).toBe("23:30");
    expect(userUses24HourClock()).toBe(true);
    await setClock({ timeZone: "UTC", hourCycle: "h12" }, "de");
    expect(plain(formatDate(at, "time"))).toBe("11:30 PM");
    expect(userUses24HourClock()).toBe(false);
    // Midnight is 12 (h12) and 0 (h23): never "0:05 AM" (h11) or "24:05" (h24).
    const midnight = new Date(Date.UTC(2026, 9, 25, 0, 5));
    expect(plain(formatDate(midnight, "time"))).toBe("12:05 AM");
    await setClock({ timeZone: "UTC", hourCycle: "h23" }, "en");
    expect(formatDate(midnight, "time")).toBe("00:05");
  });

  it("formats another zone when one is given", async () => {
    await setClock({ timeZone: "Pacific/Kiritimati", hourCycle: "h12" });
    expect(plain(formatDate(at, "time", { timeZone: "America/New_York" }))).toBe("7:30 PM");
  });

  it.each([
    ["monthDay", "Oct 25"],
    ["monthDayYear", "Oct 25, 2026"],
    ["longWeekdayDate", "Sunday, Oct 25"],
    ["fullDate", "Sunday, October 25, 2026"],
    ["monthYear", "October 2026"],
    ["timeWithSeconds", "7:30:00 PM"],
  ] as const)("writes %s as %s", async (style, expected) => {
    await setClock({ timeZone: "America/New_York", hourCycle: "h12" });
    expect(plain(formatDate(at, style))).toBe(expected);
  });
});

describe("formatter cache", () => {
  const at = new Date(Date.UTC(2026, 9, 25, 15, 5));

  it("builds one formatter per language, zone, hour cycle and style, however many dates", async () => {
    await setClock({ timeZone: "Asia/Kathmandu", hourCycle: "h12" }, "fr");
    const built = jest.spyOn(Intl, "DateTimeFormat");
    for (let i = 0; i < 500; i++) formatDate(new Date(at.getTime() + i * 60_000), "time");
    expect(built).toHaveBeenCalledTimes(1);
    for (let i = 0; i < 500; i++) formatDate(at, "monthDay");
    expect(built).toHaveBeenCalledTimes(2);
  });

  it("reflects a change of zone, hour cycle or language at the next call", async () => {
    await setClock({ timeZone: "UTC", hourCycle: "h12" }, "en");
    expect(plain(formatDate(at, "time"))).toBe("3:05 PM");
    await setClock({ timeZone: "Asia/Kathmandu", hourCycle: "h12" }, "en");
    expect(plain(formatDate(at, "time"))).toBe("8:50 PM");
    await setClock({ timeZone: "Asia/Kathmandu", hourCycle: "h23" }, "en");
    expect(formatDate(at, "time")).toBe("20:50");
    await setClock({ timeZone: "Asia/Kathmandu", hourCycle: "h23" }, "es");
    expect(formatDate(at, "weekdayDate")).toBe("dom, 25 oct");
    // Back again: the earlier formatters are reused, never the wrong one.
    await setClock({ timeZone: "UTC", hourCycle: "h12" }, "en");
    expect(plain(formatDate(at, "time"))).toBe("3:05 PM");
  });

  it("an hour cycle change leaves date-only formatters alone", async () => {
    await setClock({ timeZone: "UTC", hourCycle: "h12" });
    formatDate(at, "monthDayYear");
    const built = jest.spyOn(Intl, "DateTimeFormat");
    await setClock({ timeZone: "UTC", hourCycle: "h23" });
    formatDate(at, "monthDayYear");
    expect(built).not.toHaveBeenCalled();
  });

  it("reads the zone again when its offset moves, with no refresh", async () => {
    await setClock({ timeZone: "UTC", hourCycle: "h23" });
    expect(formatDate(at, "time")).toBe("15:05");
    // The phone flew to New York: the offset of now changes before anything else does.
    mockPhone = { timeZone: "America/New_York", hourCycle: "h23" };
    const moved = new Date().getTimezoneOffset() + 60;
    jest.spyOn(Date.prototype, "getTimezoneOffset").mockReturnValue(moved);
    expect(formatDate(at, "time")).toBe("11:05");
  });
});

describe("telling translated views", () => {
  it("sends DATE_FORMAT_CHANGED once after a change, never inside the call", async () => {
    await setClock({ timeZone: "UTC", hourCycle: "h12" });
    const changed = jest.fn();
    i18n.on(DATE_FORMAT_CHANGED, changed);
    try {
      mockPhone = { timeZone: "UTC", hourCycle: "h23" };
      refreshPhoneClock();
      expect(changed).not.toHaveBeenCalled();
      await Promise.resolve();
      expect(changed).toHaveBeenCalledTimes(1);
      refreshPhoneClock();
      await Promise.resolve();
      expect(changed).toHaveBeenCalledTimes(1);
    } finally {
      i18n.off(DATE_FORMAT_CHANGED, changed);
    }
  });

  it("sends it when only the phone's first day of the week changes, and keeps the setting", async () => {
    await setClock({ timeZone: "UTC", hourCycle: "h12", weekStart: 0 });
    expect(userWeekStart()).toBe(0);
    const changed = jest.fn();
    i18n.on(DATE_FORMAT_CHANGED, changed);
    try {
      mockPhone = { timeZone: "UTC", hourCycle: "h12", weekStart: 1 };
      refreshPhoneClock();
      await Promise.resolve();
      expect(changed).toHaveBeenCalledTimes(1);
      expect(userWeekStart()).toBe(1);
    } finally {
      i18n.off(DATE_FORMAT_CHANGED, changed);
    }
  });

  it("re-renders useTranslation views on it, as on a language change", () => {
    const bound = String(i18n.options.react?.bindI18n ?? "").split(" ");
    expect(bound).toEqual(expect.arrayContaining(["languageChanged", DATE_FORMAT_CHANGED]));
  });
});

describe("formatMinuteOfDay", () => {
  // Days a zone's clock skips an hour: US (2:00) and Chile (0:00). The label is the
  // same on them; it was not under TZ=America/New_York or TZ=America/Santiago.
  it.each([new Date(2026, 2, 8, 12), new Date(2026, 8, 6, 12), new Date(2026, 10, 1, 12)])(
    "labels a minute of the day the same on %s",
    (today) => {
      jest.useFakeTimers({ now: today });
      try {
        expect(plain(formatMinuteOfDay(0))).toBe("12:00 AM");
        expect(plain(formatMinuteOfDay(150))).toBe("2:30 AM");
        expect(plain(formatMinuteOfDay(1439))).toBe("11:59 PM");
      } finally {
        jest.useRealTimers();
      }
    },
  );

  it("follows the phone's hour cycle unless a dial holds another", async () => {
    await setClock({ timeZone: "Pacific/Kiritimati", hourCycle: "h23" }, "de");
    expect(formatMinuteOfDay(1290)).toBe("21:30");
    expect(plain(formatMinuteOfDay(1290, "h12"))).toBe("9:30 PM");
  });
});

describe("formatCalendarDay", () => {
  it.each(["UTC", "America/New_York", "Pacific/Kiritimati"])("keeps the day in %s", async (zone) => {
    await setClock({ timeZone: zone, hourCycle: "h23" });
    expect(formatCalendarDay("2026-10-16", "monthDay")).toBe("Oct 16");
    expect(formatCalendarDay("2026-10-16", "monthDayYear")).toBe("Oct 16, 2026");
  });

  it("is null for anything but a day", () => {
    expect(formatCalendarDay("not a day", "monthDay")).toBeNull();
    expect(formatCalendarDay("2026-10-16T09:00:00Z", "monthDay")).toBeNull();
  });
});

describe("wallClock", () => {
  it("reads the numbers in the zone, Kathmandu's quarter hour included", () => {
    const at = new Date(Date.UTC(2026, 9, 25, 23, 30, 9));
    expect(wallClock(at, "Asia/Kathmandu")).toEqual({
      year: 2026,
      month: 10,
      day: 26,
      hour: 5,
      minute: 15,
      second: 9,
    });
  });
});

describe("formatTimeZoneName", () => {
  const instant = new Date(Date.UTC(2026, 9, 24, 6, 0));

  it.each([
    ["America/New_York", "EDT"],
    ["UTC", "UTC"],
  ])("names %s as %s", (zone, name) => {
    expect(formatTimeZoneName(instant, zone)).toBe(name);
  });

  it("returns null for an unknown zone", () => {
    expect(formatTimeZoneName(instant, "Not/AZone")).toBeNull();
  });

  describe("when the engine names an offset zone plain GMT (Hermes)", () => {
    const real = Intl.DateTimeFormat.prototype.formatToParts;
    beforeEach(() => {
      jest
        .spyOn(Intl.DateTimeFormat.prototype, "formatToParts")
        .mockImplementation(function (this: Intl.DateTimeFormat, ...args) {
          return real
            .apply(this, args)
            .map((part) => (part.type === "timeZoneName" ? { ...part, value: "GMT" } : part));
        });
    });

    it.each([
      ["Africa/Nairobi", "GMT+3"],
      ["Asia/Kolkata", "GMT+5:30"],
      ["America/Los_Angeles", "GMT-7"],
      ["Europe/London", "GMT+1"],
      ["Atlantic/Reykjavik", "GMT"],
    ])("gives %s its offset, %s", (zone, label) => {
      expect(formatTimeZoneName(instant, zone)).toBe(label);
    });
  });
});
