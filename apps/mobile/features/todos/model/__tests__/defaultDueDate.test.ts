import { defaultDueDate } from "@/features/todos/model/dueDate";

describe("defaultDueDate", () => {
  afterEach(() => jest.useRealTimers());

  it("is 9:00 today before nine in the morning", () => {
    jest.useFakeTimers({ now: new Date(2026, 9, 19, 7, 30) });
    expect(defaultDueDate()).toEqual(new Date(2026, 9, 19, 9, 0, 0, 0));
  });

  it("is the next whole hour from nine on", () => {
    jest.useFakeTimers({ now: new Date(2026, 9, 19, 9, 0) });
    expect(defaultDueDate()).toEqual(new Date(2026, 9, 19, 10, 0, 0, 0));
    jest.setSystemTime(new Date(2026, 9, 19, 23, 40));
    expect(defaultDueDate()).toEqual(new Date(2026, 9, 20, 0, 0, 0, 0));
  });
});
