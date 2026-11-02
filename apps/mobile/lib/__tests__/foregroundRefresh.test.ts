import { AppState } from "react-native";

import { onAppStateChange } from "@/lib/foregroundRefresh";

const handlers: ((state: string) => void)[] = [];
const removed = jest.fn();
jest.mock("react-native", () => ({
  AppState: {
    addEventListener: jest.fn((_event: string, handler: (state: string) => void) => {
      handlers.push(handler);
      return { remove: () => { removed(); handlers.splice(handlers.indexOf(handler), 1); } };
    }),
  },
}));

it("fans one native AppState listener out to every subscriber (NET-16)", () => {
  const first = jest.fn();
  const second = jest.fn();
  const stopFirst = onAppStateChange(first);
  const stopSecond = onAppStateChange(second);
  expect(AppState.addEventListener).toHaveBeenCalledTimes(1);

  handlers[0]("active");
  expect(first).toHaveBeenCalledWith("active", false);
  expect(second).toHaveBeenCalledWith("active", false);

  stopFirst();
  handlers[0]("background");
  expect(first).toHaveBeenCalledTimes(1);
  expect(second).toHaveBeenCalledWith("background", false);

  // The last one out removes the native listener; the next one in adds it again.
  stopSecond();
  expect(removed).toHaveBeenCalledTimes(1);
  expect(handlers).toHaveLength(0);
  const stopThird = onAppStateChange(jest.fn());
  expect(AppState.addEventListener).toHaveBeenCalledTimes(2);
  stopThird();
});

it("calls only an active after background a return; an iOS inactive blip is none", () => {
  const seen: string[] = [];
  const stop = onAppStateChange((state, returned) => seen.push(`${state}${returned ? " (return)" : ""}`));
  // Control Centre and back, then out to the home screen and back.
  for (const state of ["inactive", "active", "inactive", "background", "active"]) handlers[0](state);
  expect(seen).toEqual(["inactive", "active", "inactive", "background", "active (return)"]);
  stop();
});

it("calls the first active a return when the app launched in the background", () => {
  (AppState as { currentState?: string }).currentState = "background";
  const seen: boolean[] = [];
  const stop = onAppStateChange((_state, returned) => seen.push(returned));
  handlers[0]("active");
  handlers[0]("inactive");
  handlers[0]("active");
  expect(seen).toEqual([true, false, false]);
  stop();
  (AppState as { currentState?: string }).currentState = undefined;
});
