import { repeatMessageKey } from "@/features/todos/model/repeatLabel";

describe("repeatMessageKey", () => {
  it.each([
    [null, "todos.repeat_none"],
    ["daily", "todos.repeat_daily"],
    ["weekly", "todos.repeat_weekly"],
  ] as const)("maps %s to %s", (rule, key) => {
    expect(repeatMessageKey(rule)).toBe(key);
  });
});
