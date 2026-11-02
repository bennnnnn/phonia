/**
 * @jest-environment ./jest.timeZoneEnvironment.js
 */
import { render } from "@testing-library/react-native";

import { CircularClockBlock } from "@/components/rich/CircularClockBlock";
import { refreshPhoneClock } from "@/lib/datetime/format";

declare const setTestTimeZone: (zone: string) => void;

// A cold start: the cached account has no zone until /auth/me answers.
jest.mock("@/contexts/AuthContext", () => ({
  useAuthOptional: () => ({ user: { timezone: "", locale: "en" } }),
}));
jest.mock("@/lib/datetime/phoneClock", () => {
  const actual = jest.requireActual<typeof import("@/lib/datetime/phoneClock")>("@/lib/datetime/phoneClock");
  return { ...actual, readPhoneClock: () => ({ timeZone: actual.deviceTimeZone(), hourCycle: "h12" }) };
});

const NOW = new Date("2026-10-25T23:30:09Z");
const spaced = (text: string) => new RegExp(`^${text.replace(/ /g, "\\s")}$`);

beforeEach(() => {
  jest.useFakeTimers({ now: NOW });
  setTestTimeZone("America/New_York");
  refreshPhoneClock();
});
afterEach(() => jest.useRealTimers());

it("shows the user's own time when the fence names no zone, not UTC", async () => {
  const view = await render(<CircularClockBlock content="" />);
  expect(view.getByText(spaced("7:30:09 PM"))).toBeTruthy();
  expect(view.getByText("Sunday, October 25, 2026")).toBeTruthy();
  expect(view.getByText("EDT")).toBeTruthy();
});

it("shows the city the fence names, in the app's way of writing dates", async () => {
  const view = await render(<CircularClockBlock content="Asia/Kathmandu" />);
  expect(view.getByText(spaced("5:15:09 AM"))).toBeTruthy();
  expect(view.getByText("Monday, October 26, 2026")).toBeTruthy();
  expect(view.getByText(/^(GMT\+5:45|NPT)$/)).toBeTruthy();
});

it("draws the user's time for a zone no engine knows instead of throwing", async () => {
  const view = await render(<CircularClockBlock content="Mars/Olympus_Mons" />);
  expect(view.getByText(spaced("7:30:09 PM"))).toBeTruthy();
});
