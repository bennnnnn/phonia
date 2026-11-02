import { watchPhoneClock } from "@/lib/datetime/phoneClockSync";

type AppStateListener = (state: string, returned: boolean) => void;

const mockRefresh = jest.fn();
const mockStopForeground = jest.fn();
const mockStopNative = jest.fn();
let mockAppState: AppStateListener | null = null;
let mockNative: (() => void) | null = null;

jest.mock("@/lib/datetime/format", () => ({ refreshPhoneClock: () => mockRefresh() }));
jest.mock("@/lib/datetime/phoneClock", () => ({
  onPhoneClockChange: (listener: () => void) => {
    mockNative = listener;
    return mockStopNative;
  },
}));
jest.mock("@/lib/foregroundRefresh", () => ({
  onAppStateChange: (listener: AppStateListener) => {
    mockAppState = listener;
    return mockStopForeground;
  },
}));

beforeEach(() => jest.clearAllMocks());

it("reads the phone's clock again on a return from the background, not on a Control Centre blip", () => {
  const stop = watchPhoneClock();
  mockAppState!("inactive", false);
  mockAppState!("active", false);
  expect(mockRefresh).not.toHaveBeenCalled();
  mockAppState!("active", true);
  expect(mockRefresh).toHaveBeenCalledTimes(1);
  stop();
});

it("reads it again when the OS reports a change, and stops both on cleanup", () => {
  const stop = watchPhoneClock();
  mockNative!();
  expect(mockRefresh).toHaveBeenCalledTimes(1);
  stop();
  expect(mockStopForeground).toHaveBeenCalledTimes(1);
  expect(mockStopNative).toHaveBeenCalledTimes(1);
});
