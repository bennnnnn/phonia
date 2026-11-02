import { StaleResourceCache } from "@/lib/cache/staleResource";

describe("StaleResourceCache", () => {
  it("returns fresh values without invoking the loader", async () => {
    const cache = new StaleResourceCache<string, number>(1_000);
    cache.set("key", 7);
    const loader = jest.fn(async () => 9);

    await expect(cache.fetch("key", loader)).resolves.toBe(7);
    expect(loader).not.toHaveBeenCalled();
  });

  it("reads again after the clock is set back", async () => {
    const cache = new StaleResourceCache<string, number>(1_000);
    cache.set("key", 7, 10_000_000);
    expect(cache.isFresh("key", 10_000_000 - 60 * 60_000)).toBe(false);
    expect(cache.isFresh("key", 10_000_500)).toBe(true);
  });

  it("deduplicates forced in-flight reads by key", async () => {
    const cache = new StaleResourceCache<string, number>(1_000);
    let resolve!: (value: number) => void;
    const loader = jest.fn(() => new Promise<number>((done) => (resolve = done)));

    const first = cache.fetch("key", loader, { force: true });
    const second = cache.fetch("key", loader, { force: true });
    resolve(11);

    await expect(Promise.all([first, second])).resolves.toEqual([11, 11]);
    expect(loader).toHaveBeenCalledTimes(1);
  });

  it("keeps keys independent", async () => {
    const cache = new StaleResourceCache<string, number>(1_000);
    await Promise.all([
      cache.fetch("a", async () => 1),
      cache.fetch("b", async () => 2),
    ]);

    expect(cache.get("a")).toBe(1);
    expect(cache.get("b")).toBe(2);
  });

  it("preserves the timestamp for local updates", () => {
    const cache = new StaleResourceCache<string, number>(1_000);
    cache.set("key", 1, 123);
    cache.update("key", (value) => (value ?? 0) + 1);

    expect(cache.getEntry("key")).toEqual({ data: 2, fetchedAt: 123 });
  });

  it("maps every cached value in place", () => {
    const cache = new StaleResourceCache<string, number[]>(1_000);
    cache.set("a", [1, 2], 10);
    cache.set("b", [2, 3], 20);
    cache.updateEach((value) => value.filter((n) => n !== 2));

    expect(cache.get("a")).toEqual([1]);
    expect(cache.get("b")).toEqual([3]);
    expect(cache.getEntry("a")?.fetchedAt).toBe(10);
  });

  it("invalidates cached and in-flight state", async () => {
    const cache = new StaleResourceCache<string, number>(1_000);
    cache.set("key", 1);
    cache.invalidate("key");

    expect(cache.get("key")).toBeUndefined();
    expect(cache.isFresh("key")).toBe(false);
  });

  it("keeps only the most recently used keys when capped", () => {
    const cache = new StaleResourceCache<string, number>(60_000, 2);
    cache.set("a", 1);
    cache.set("b", 2);
    cache.get("a"); // a is now newer than b
    cache.set("c", 3);
    expect(cache.get("a")).toBe(1);
    expect(cache.get("b")).toBeUndefined();
    expect(cache.get("c")).toBe(3);
  });
});
