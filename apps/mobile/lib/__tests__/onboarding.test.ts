jest.mock("@/lib/filePrefs", () => ({
  prefFilePath: (name: string) => `file:///docs/${name}`,
  readPrefFile: jest.fn(),
  writePrefFile: jest.fn(),
}));

function load(stored: { value: string | null }) {
  const prefs = jest.requireMock("@/lib/filePrefs");
  prefs.readPrefFile.mockImplementation(async () => stored.value);
  prefs.writePrefFile.mockImplementation(async (_path: string, value: string) => {
    stored.value = value;
  });
  const onboarding = jest.requireActual<typeof import("@/lib/onboarding")>("@/lib/onboarding");
  return { ...onboarding, prefs };
}

beforeEach(() => jest.resetModules());

it("keeps completed onboarding across module reload", async () => {
  const stored = { value: null as string | null };
  await load(stored).setOnboarded();
  jest.resetModules();
  await expect(load(stored).getOnboarded()).resolves.toBe(true);
});

it("a clear takes precedence over a stored flag", async () => {
  const stored = { value: "1" as string | null };
  const first = load(stored);
  await expect(first.getOnboarded()).resolves.toBe(true);
  await first.clearOnboarded();
  jest.resetModules();
  await expect(load(stored).getOnboarded()).resolves.toBe(false);
});

it("does not restore a flag from a read that completes after sign-out", async () => {
  const stored = { value: null as string | null };
  const current = load(stored);
  let finishRead!: (value: string | null) => void;
  current.prefs.readPrefFile.mockImplementationOnce(() => new Promise((resolve) => {
    finishRead = resolve;
  }));
  const reading = current.getOnboarded();
  await current.clearOnboarded();
  finishRead(null);
  await expect(reading).resolves.toBe(false);
  expect(stored.value).toBe("0");
});

it("serializes completion and sign-out when a disk write is already pending", async () => {
  const stored = { value: null as string | null };
  const current = load(stored);
  let finishWrite!: () => void;
  const started = new Promise<void>((resolveStarted) => {
    current.prefs.writePrefFile.mockImplementationOnce(async (_path: string, value: string) => {
      resolveStarted();
      await new Promise<void>((resolve) => { finishWrite = resolve; });
      stored.value = value;
    });
  });
  const completing = current.setOnboarded();
  await started;
  const clearing = current.clearOnboarded();
  finishWrite();
  await Promise.all([completing, clearing]);
  jest.resetModules();
  await expect(load(stored).getOnboarded()).resolves.toBe(false);
});
