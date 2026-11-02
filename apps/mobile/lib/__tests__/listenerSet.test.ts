import { createListenerSet, createValueStore } from "@/lib/listenerSet";

describe("createListenerSet", () => {
  it("calls listeners in subscription order with the emitted arguments", () => {
    const set = createListenerSet<[number, string]>();
    const calls: string[] = [];
    set.subscribe((n, label) => calls.push(`a:${n}:${label}`));
    set.subscribe((n, label) => calls.push(`b:${n}:${label}`));
    set.emit(1, "x");
    expect(calls).toEqual(["a:1:x", "b:1:x"]);
  });

  it("stops calling a listener once it unsubscribes, and unsubscribing twice is harmless", () => {
    const set = createListenerSet();
    const listener = jest.fn();
    const unsubscribe = set.subscribe(listener);
    unsubscribe();
    unsubscribe();
    set.emit();
    expect(listener).not.toHaveBeenCalled();
  });

  it("subscribes a listener once however often it is added", () => {
    const set = createListenerSet();
    const listener = jest.fn();
    set.subscribe(listener);
    set.subscribe(listener);
    set.emit();
    expect(listener).toHaveBeenCalledTimes(1);
  });

  it("follows Set iteration: a listener added mid-emit runs, one removed before its turn does not", () => {
    const set = createListenerSet();
    const late = jest.fn();
    const removed = jest.fn();
    let unsubscribeRemoved = () => {};
    set.subscribe(() => {
      set.subscribe(late);
      unsubscribeRemoved();
    });
    unsubscribeRemoved = set.subscribe(removed);
    set.emit();
    expect(late).toHaveBeenCalledTimes(1);
    expect(removed).not.toHaveBeenCalled();
  });

  it("clear drops every listener", () => {
    const set = createListenerSet();
    const listener = jest.fn();
    set.subscribe(listener);
    set.clear();
    set.emit();
    expect(listener).not.toHaveBeenCalled();
  });
});

describe("createValueStore", () => {
  it("notifies only when the value changes", () => {
    const store = createValueStore("system");
    const listener = jest.fn();
    store.subscribe(listener);
    store.set("system");
    expect(listener).not.toHaveBeenCalled();
    store.set("dark");
    expect(store.get()).toBe("dark");
    expect(listener).toHaveBeenCalledTimes(1);
  });

  it("reset restores the initial value and drops listeners", () => {
    const store = createValueStore(1);
    const listener = jest.fn();
    store.subscribe(listener);
    store.set(2);
    store.reset();
    expect(store.get()).toBe(1);
    store.set(3);
    expect(listener).toHaveBeenCalledTimes(1);
  });
});
