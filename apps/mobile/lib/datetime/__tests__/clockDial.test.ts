import {
  angleForHour,
  angleForMinute,
  dayPeriodLabels,
  from12Hour,
  hourAtAngle,
  hourLabel,
  hourOnInnerRing,
  minuteAtAngle,
  minutesFromTime,
  parseHourInput,
  parseMinuteInput,
  pointOnDial,
  pointToAngle,
  timeFromMinutes,
  to12Hour,
  touchesInnerRing,
  withDayHalf,
  withTimeOfDay,
} from "@/lib/datetime/clockDial";
import { ensureLocale } from "@/lib/i18n";

describe("pointToAngle", () => {
  it.each([
    [0, -10, 0],
    [10, 0, 90],
    [0, 10, 180],
    [-10, 0, 270],
    [10, -10, 45],
  ])("(%i, %i) is %i° clockwise from 12", (dx, dy, angle) => {
    expect(pointToAngle(dx, dy)).toBeCloseTo(angle);
  });

  it("round-trips through pointOnDial", () => {
    for (const angle of [0, 30, 135, 250, 330]) {
      const { x, y } = pointOnDial(angle, 100, 128);
      expect(pointToAngle(x - 128, y - 128)).toBeCloseTo(angle);
    }
  });
});

describe("hourAtAngle", () => {
  it.each([
    [0, false, 0],
    [0, true, 12],
    [30, false, 1],
    [270, true, 21],
    [14, false, 0],
    [16, false, 1],
    [345, false, 0],
  ])("12-hour dial at %i° with pm=%s is %i", (angle, pm, hour) => {
    expect(hourAtAngle(angle, { is24Hour: false, inner: false, pm })).toBe(hour);
  });

  it.each([
    [0, false, 12],
    [0, true, 0],
    [30, false, 1],
    [30, true, 13],
    [330, false, 11],
    [330, true, 23],
  ])("24-hour dial at %i° on the inner ring=%s is %i", (angle, inner, hour) => {
    expect(hourAtAngle(angle, { is24Hour: true, inner, pm: false })).toBe(hour);
  });

  it("puts 00 and 13–23 on the inner ring of a 24-hour dial only", () => {
    expect(hourOnInnerRing(0, true)).toBe(true);
    expect(hourOnInnerRing(13, true)).toBe(true);
    expect(hourOnInnerRing(12, true)).toBe(false);
    expect(hourOnInnerRing(5, true)).toBe(false);
    expect(hourOnInnerRing(15, false)).toBe(false);
  });

  it("splits the rings halfway between them", () => {
    expect(touchesInnerRing(70, 100, 60)).toBe(true);
    expect(touchesInnerRing(90, 100, 60)).toBe(false);
  });
});

describe("minuteAtAngle", () => {
  it.each([
    [0, 1, 0],
    [6, 1, 1],
    [66, 1, 11],
    [357, 1, 0],
    [354, 1, 59],
    [66, 5, 10],
    [80, 5, 15],
    [358, 5, 0],
  ])("%i° with a %i-minute step is %i", (angle, step, minute) => {
    expect(minuteAtAngle(angle, step)).toBe(minute);
  });

  it("maps values back to their angle", () => {
    expect(angleForMinute(15)).toBe(90);
    expect(angleForHour(15)).toBe(90);
    expect(angleForHour(0)).toBe(0);
  });
});

describe("12-hour conversion", () => {
  it.each([
    [0, 12, false],
    [9, 9, false],
    [12, 12, true],
    [21, 9, true],
  ])("%i:00 reads %i with pm=%s and converts back", (hour24, hour12, pm) => {
    expect(to12Hour(hour24)).toEqual({ hour: hour12, pm });
    expect(from12Hour(hour12, pm)).toBe(hour24);
  });

  it("moves an hour between the morning and the afternoon", () => {
    expect(withDayHalf(9, true)).toBe(21);
    expect(withDayHalf(21, false)).toBe(9);
    expect(withDayHalf(0, true)).toBe(12);
    expect(withDayHalf(12, false)).toBe(0);
  });

  it("labels the hour for the clock in use", () => {
    expect(hourLabel(21, false)).toBe("9");
    expect(hourLabel(0, false)).toBe("12");
    expect(hourLabel(9, true)).toBe("09");
    expect(hourLabel(0, true)).toBe("00");
  });
});

describe("typed entry", () => {
  it.each([
    ["9", false, 9],
    ["12", false, 12],
    ["0", false, null],
    ["13", false, null],
    ["0", true, 0],
    ["23", true, 23],
    ["24", true, null],
    ["", true, null],
    ["1a", true, null],
    [" 7 ", false, 7],
  ])("hour %j on a 24-hour clock=%s is %s", (text, is24Hour, hour) => {
    expect(parseHourInput(text, is24Hour)).toBe(hour);
  });

  it.each([
    ["0", 0],
    ["05", 5],
    ["59", 59],
    ["60", null],
    ["123", null],
    ["-1", null],
  ])("minute %j is %s", (text, minute) => {
    expect(parseMinuteInput(text)).toBe(minute);
  });
});

describe("time helpers", () => {
  it("converts minutes of the day, wrapping past midnight", () => {
    expect(timeFromMinutes(1320)).toEqual({ hour: 22, minute: 0 });
    expect(timeFromMinutes(1445)).toEqual({ hour: 0, minute: 5 });
    expect(timeFromMinutes(-60)).toEqual({ hour: 23, minute: 0 });
    expect(minutesFromTime({ hour: 7, minute: 30 })).toBe(450);
  });

  it("sets a time on a copy of a date", () => {
    const date = new Date(2026, 8, 26, 8, 15, 42);
    const next = withTimeOfDay(date, { hour: 21, minute: 5 });
    expect(next.getHours()).toBe(21);
    expect(next.getMinutes()).toBe(5);
    expect(next.getSeconds()).toBe(0);
    expect(next.getDate()).toBe(26);
    expect(date.getHours()).toBe(8);
  });
});

describe("day periods", () => {
  afterEach(() => ensureLocale("en"));

  it("reads AM and PM in the app's language", async () => {
    expect(dayPeriodLabels()).toEqual({ am: "AM", pm: "PM" });
    await ensureLocale("es");
    const spanish = dayPeriodLabels();
    expect(spanish.am.replace(/\s/g, " ")).toBe("a. m.");
    expect(spanish.pm.replace(/\s/g, " ")).toBe("p. m.");
  });
});
