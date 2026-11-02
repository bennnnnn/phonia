/**
 * @jest-environment ./jest.timeZoneEnvironment.js
 */
import { render } from "@testing-library/react-native";

import { TodoDateFields } from "@/features/todos/components/TodoDateFields";
import { TodosScrollList } from "@/features/todos/components/TodosScrollList";
import { describeDueAt } from "@/features/todos/model/dueDate";
import { buildTodoListRows } from "@/features/todos/model/todoListRows";
import type { Todo } from "@/lib/api";
import { formatDate, refreshPhoneClock } from "@/lib/datetime/format";
import type { HourCycle } from "@/lib/datetime/phoneClock";
import { ensureLocale } from "@/lib/i18n";

declare const setTestTimeZone: (zone: string) => void;

// The row read the language through this hook and the editor read the phone's locale:
// with the app in German on an English phone they wrote one time two ways.
let mockLanguage = "en";
jest.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key, i18n: { language: mockLanguage } }),
  initReactI18next: { type: "3rdParty", init: () => undefined },
}));
// The real zone (the engine's, which TZ sets); the phone's 24-Hour Time switch.
let mockHourCycle: HourCycle = "h12";
jest.mock("@/lib/datetime/phoneClock", () => {
  const actual = jest.requireActual<typeof import("@/lib/datetime/phoneClock")>("@/lib/datetime/phoneClock");
  return { ...actual, readPhoneClock: () => ({ timeZone: actual.deviceTimeZone(), hourCycle: mockHourCycle }) };
});
jest.mock("@shopify/flash-list", () => {
  const React = jest.requireActual<typeof import("react")>("react");
  return {
    FlashList: ({ data, renderItem, keyExtractor }: {
      data: { key: string }[];
      renderItem: (info: { item: unknown; index: number }) => React.ReactNode;
      keyExtractor: (item: unknown) => string;
    }) => React.createElement(React.Fragment, null, ...data.map((item, index) =>
      React.createElement(React.Fragment, { key: keyExtractor(item) }, renderItem({ item, index })))),
  };
});
jest.mock("react-native-gesture-handler/ReanimatedSwipeable", () => {
  const { View } = jest.requireActual("react-native");
  return { __esModule: true, default: View };
});
jest.mock("@/features/todos/model/todoReminders", () => ({
  ensureNotificationPermission: jest.fn(async () => true),
}));

/** 23:30 UTC: Oct 25 in UTC and New York, already Oct 26 in Kathmandu and Kiritimati. */
const DUE = "2026-10-25T23:30:00.000Z";
/** Five or six days earlier in every zone: the to-do sits under its own day's heading. */
const NOW = new Date("2026-10-20T12:00:00Z");

const todo = {
  id: "t1", content: "Call Sam", topic: "General", checked: false, due_at: DUE, recurrence_rule: null,
  sort_order: null, chat_id: null, created_at: "2026-10-01T00:00:00Z", updated_at: "2026-10-01T00:00:00Z",
} as Todo;

const plain = (text: string) => text.replace(/\s/g, " ");
/** The exact text, whichever space ICU put before AM/PM. */
const spaced = (text: string) => new RegExp(`^${text.replace(/ /g, "\\s")}$`);

type Expected = { heading: string; date: string; twelve: string; twentyFour: string };

const EXPECTED: Record<string, Record<"en" | "de", Expected>> = {
  UTC: {
    en: { heading: "Sunday, Oct 25", date: "Oct 25, 2026", twelve: "11:30 PM", twentyFour: "23:30" },
    de: { heading: "Sonntag, 25. Okt.", date: "25. Okt. 2026", twelve: "11:30 PM", twentyFour: "23:30" },
  },
  "America/New_York": {
    en: { heading: "Sunday, Oct 25", date: "Oct 25, 2026", twelve: "7:30 PM", twentyFour: "19:30" },
    de: { heading: "Sonntag, 25. Okt.", date: "25. Okt. 2026", twelve: "7:30 PM", twentyFour: "19:30" },
  },
  "Asia/Kathmandu": {
    en: { heading: "Monday, Oct 26", date: "Oct 26, 2026", twelve: "5:15 AM", twentyFour: "05:15" },
    de: { heading: "Montag, 26. Okt.", date: "26. Okt. 2026", twelve: "5:15 AM", twentyFour: "5:15" },
  },
  "Pacific/Kiritimati": {
    en: { heading: "Monday, Oct 26", date: "Oct 26, 2026", twelve: "1:30 PM", twentyFour: "13:30" },
    de: { heading: "Montag, 26. Okt.", date: "26. Okt. 2026", twelve: "1:30 PM", twentyFour: "13:30" },
  },
};

const CASES = Object.keys(EXPECTED).flatMap((zone) =>
  (["en", "de"] as const).flatMap((language) =>
    (["h12", "h23"] as const).map((hourCycle) => [zone, language, hourCycle] as const)));

afterAll(() => ensureLocale("en"));

describe.each(CASES)("in %s, the app in %s, a %s phone", (zone, language, hourCycle) => {
  const expected = EXPECTED[zone][language];
  const time = hourCycle === "h12" ? expected.twelve : expected.twentyFour;

  beforeEach(async () => {
    setTestTimeZone(zone);
    mockHourCycle = hourCycle;
    // What a return from the phone's Settings does (phoneClockSync.ts).
    refreshPhoneClock();
    mockLanguage = language;
    await ensureLocale(language);
  });

  it("the to-do row, its day heading and its editor say the same day and time", async () => {
    const noop = jest.fn();
    const rows = buildTodoListRows([todo], NOW);
    const list = await render(
      <TodosScrollList rows={rows} now={NOW} showEmpty={false} error={false} listHeader={<></>}
        busyTodoIds={new Set()} onToggle={noop} onOpen={noop} onDeleteItem={noop} />,
    );
    // Grouped by the user's day, headed by the same day.
    expect(rows[0]).toMatchObject({ kind: "heading", section: "date" });
    expect(list.getByText(expected.heading)).toBeTruthy();
    const rowTime = list.getByLabelText(new RegExp(`^Call Sam, `)).props.accessibilityLabel.slice("Call Sam, ".length);
    await list.unmount();

    const editor = await render(
      <TodoDateFields review dueDate={new Date(DUE)} onDueDateChange={noop} repeat={null}
        onRepeatChange={noop} todos={[]} onOpen={noop} />,
    );
    expect(editor.getByText(expected.date)).toBeTruthy();
    expect(plain(rowTime)).toBe(time);
    expect(editor.getByText(spaced(time))).toBeTruthy();
  });

  it("the to-do's due label counts days and writes its time in the same zone", () => {
    jest.useFakeTimers({ now: new Date("2026-10-25T23:00:00Z") });
    try {
      // Half an hour before it falls due in UTC: the day and time the row shows.
      const today = new Date("2026-10-25T23:00:00Z").getDate() === new Date(DUE).getDate();
      const label = plain(describeDueAt(DUE)?.label ?? "");
      if (today) expect(label).toBe(`${language === "de" ? "Heute" : "Today"} ${time}`);
      else expect(label).toBe(language === "de" ? "Morgen" : "Tomorrow");
    } finally {
      jest.useRealTimers();
    }
  });
});

it("follows the phone to a new zone with no refresh: the zone's offset moved", async () => {
  await ensureLocale("en");
  setTestTimeZone("UTC");
  mockHourCycle = "h23";
  refreshPhoneClock();
  for (const [zone, expected] of Object.entries(EXPECTED)) {
    setTestTimeZone(zone);
    expect(formatDate(new Date(DUE), "time")).toBe(expected.en.twentyFour);
    expect(formatDate(new Date(DUE), "monthDayYear")).toBe(expected.en.date);
  }
});
