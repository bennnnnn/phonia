const { execFileSync } = jest.requireActual("node:child_process");
const path = jest.requireActual("node:path");

it("keeps Expo URL parsing compatible and finishes malformed input in bounded time", () => {
  const output = execFileSync(process.execPath, [
    path.resolve("scripts/check-url-dependencies.cjs"),
  ], { encoding: "utf8", timeout: 5000 });
  expect(output).toContain("URL dependencies are compatible");
});
