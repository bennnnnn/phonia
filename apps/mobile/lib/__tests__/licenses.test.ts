import licenses from "@/lib/licenses.generated.json";

// The lib test project has Jest types but no Node types (see katexParity.test.ts).
declare const __dirname: string;
const { readFileSync } = jest.requireActual<{
  readFileSync(path: string, encoding: "utf8"): string;
}>("node:fs");
const { join } = jest.requireActual<{ join(...parts: string[]): string }>("node:path");

const root = join(__dirname, "..", "..");
const { dependencies } = JSON.parse(readFileSync(join(root, "package.json"), "utf8")) as {
  dependencies: Record<string, string>;
};

describe("open-source licenses page", () => {
  it("lists every shipped dependency at its installed version (run `pnpm oss-licenses`)", () => {
    const listed = new Map(licenses.map((entry) => [entry.name, entry]));
    const stale = Object.keys(dependencies).filter((name) => {
      const installed = JSON.parse(
        readFileSync(join(root, "node_modules", name, "package.json"), "utf8"),
      ) as { version: string };
      return listed.get(name)?.version !== installed.version;
    });
    expect(stale).toEqual([]);
  });

  it("names a license for every package", () => {
    expect(licenses.filter((entry) => !entry.license || entry.license === "UNKNOWN")).toEqual([]);
  });
});
