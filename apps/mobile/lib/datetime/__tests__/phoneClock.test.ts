type PhoneClockModule = typeof import("@/lib/datetime/phoneClock");

type FakeLocalization = {
  getCalendars: jest.Mock;
  addListener: jest.Mock;
};

let mockLocalization: FakeLocalization | null = null;
jest.mock("expo-modules-core", () => ({
  requireOptionalNativeModule: (name: string) => (name === "ExpoLocalization" ? mockLocalization : null),
}));

/** A fresh copy: the module keeps the native module it found. */
function load(localization: FakeLocalization | null): PhoneClockModule {
  mockLocalization = localization;
  let loaded: PhoneClockModule | undefined;
  jest.isolateModules(() => {
    loaded = jest.requireActual<PhoneClockModule>("@/lib/datetime/phoneClock");
  });
  return loaded!;
}

function localization(uses24hourClock: boolean | null): FakeLocalization {
  return {
    getCalendars: jest.fn(() => [{ calendar: "gregory", timeZone: "Asia/Kathmandu", uses24hourClock, firstWeekday: 1 }]),
    addListener: jest.fn(() => ({ remove: jest.fn() })),
  };
}

describe("readPhoneClock", () => {
  it.each([
    [true, "h23"],
    [false, "h12"],
  ])("maps the phone's 24-Hour Time switch %s to %s", (uses24, hourCycle) => {
    expect(load(localization(uses24)).readPhoneClock().hourCycle).toBe(hourCycle);
  });

  it("reads the switch again on each read, so a change in Settings shows", () => {
    const native = localization(false);
    const { readPhoneClock } = load(native);
    expect(readPhoneClock().hourCycle).toBe("h12");
    native.getCalendars.mockReturnValue([{ uses24hourClock: true }]);
    expect(readPhoneClock().hourCycle).toBe("h23");
  });

  it.each([
    ["a build without the module", null],
    ["a module that cannot tell", localization(null)],
  ])("falls back to the phone locale's own clock for %s", (_label, native) => {
    const { localeUses24HourClock, readPhoneClock } = load(native);
    expect(readPhoneClock().hourCycle).toBe(localeUses24HourClock() ? "h23" : "h12");
  });

  it("falls back when the native call throws", () => {
    const native = localization(true);
    native.getCalendars.mockImplementation(() => {
      throw new Error("gone");
    });
    const { localeUses24HourClock, readPhoneClock } = load(native);
    expect(readPhoneClock().hourCycle).toBe(localeUses24HourClock() ? "h23" : "h12");
  });

  it("takes the zone from the engine, the one local Date fields use", () => {
    const { deviceTimeZone, readPhoneClock } = load(localization(true));
    const engine = Intl.DateTimeFormat().resolvedOptions().timeZone;
    // Run with TZ="" the engine knows no zone: the case below.
    expect(readPhoneClock().timeZone).toBe(engine === "Etc/Unknown" ? undefined : engine);
    expect(deviceTimeZone()).toBe(readPhoneClock().timeZone);
  });

  it("has no zone when the engine could not find one out: no formatter takes Etc/Unknown", () => {
    const resolved = Intl.DateTimeFormat.prototype.resolvedOptions;
    const spy = jest.spyOn(Intl.DateTimeFormat.prototype, "resolvedOptions").mockImplementation(function (
      this: Intl.DateTimeFormat,
    ) {
      return { ...resolved.call(this), timeZone: "Etc/Unknown" };
    });
    try {
      const { deviceTimeZone, readPhoneClock } = load(localization(true));
      expect(deviceTimeZone()).toBeUndefined();
      const zone = readPhoneClock().timeZone;
      expect(zone).toBeUndefined();
      expect(() => new Intl.DateTimeFormat("en", { timeZone: zone }).format(new Date(0))).not.toThrow();
    } finally {
      spy.mockRestore();
    }
  });
});

describe("readPhoneClock's week start", () => {
  function phoneWithWeek(firstWeekday: unknown): FakeLocalization {
    const native = localization(true);
    native.getCalendars.mockReturnValue([{ uses24hourClock: true, firstWeekday }]);
    return native;
  }

  // expo-localization 57.0.2: 1 = Sunday … 7 = Saturday (its Weekday enum, iOS's
  // Calendar.firstWeekday, Android's Calendar.getFirstDayOfWeek()); Date.getDay() is 0-based.
  it.each([
    [1, 0],
    [2, 1],
    [7, 6],
  ])("maps the phone's First Day of Week %i to weekday %i", (firstWeekday, weekStart) => {
    expect(load(phoneWithWeek(firstWeekday)).readPhoneClock().weekStart).toBe(weekStart);
  });

  it.each([[null], [0], [8], [1.5], ["2"]])("leaves out a first weekday of %p it cannot map", (firstWeekday) => {
    expect(load(phoneWithWeek(firstWeekday)).readPhoneClock().weekStart).toBeUndefined();
  });

  it("leaves it out in a build without the module, or when the native call throws", () => {
    expect(load(null).readPhoneClock().weekStart).toBeUndefined();
    const native = localization(true);
    native.getCalendars.mockImplementation(() => {
      throw new Error("gone");
    });
    expect(load(native).readPhoneClock().weekStart).toBeUndefined();
  });

  it("reads the setting again on each read, so a change in Settings shows", () => {
    const native = phoneWithWeek(1);
    const { readPhoneClock } = load(native);
    expect(readPhoneClock().weekStart).toBe(0);
    native.getCalendars.mockReturnValue([{ uses24hourClock: true, firstWeekday: 2 }]);
    expect(readPhoneClock().weekStart).toBe(1);
  });
});

describe("localeUses24HourClock", () => {
  it.each([
    ["en-US", false],
    ["de-DE", true],
    ["fr-FR", true],
    ["ru-RU", true],
    ["en-GB", true],
  ])("%s uses a 24-hour clock: %s", (locale, expected) => {
    expect(load(null).localeUses24HourClock(locale)).toBe(expected);
  });
});

describe("onPhoneClockChange", () => {
  it("listens for the OS's calendar change and stops", () => {
    const native = localization(true);
    const remove = jest.fn();
    native.addListener.mockReturnValue({ remove });
    const listener = jest.fn();
    const stop = load(native).onPhoneClockChange(listener);
    expect(native.addListener).toHaveBeenCalledWith("onCalendarSettingsChanged", listener);
    stop();
    expect(remove).toHaveBeenCalledTimes(1);
  });

  it("is a no-op in a build without the module", () => {
    expect(() => load(null).onPhoneClockChange(jest.fn())()).not.toThrow();
  });
});
