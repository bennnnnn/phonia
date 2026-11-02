// Exercise the real Expo dependency chain with Node's CommonJS loader.
const assert = require("node:assert/strict");
const { createRequire } = require("node:module");

const fromRouter = createRequire(require.resolve("expo-router/package.json"));
const queryString = fromRouter("query-string");
const fromQueryString = createRequire(fromRouter.resolve("query-string"));
const decode = fromQueryString("decode-uri-component");
assert.equal(typeof decode, "function");

assert.equal(queryString.parse("q=a+b").q, "a b");
assert.equal(queryString.parse("q=a%2Bb").q, "a+b");
assert.equal(queryString.parse("q=caf%C3%A9+%F0%9F%8C%8D").q, "café 🌍");
assert.equal(queryString.parse("q=%41%ZZ").q, "A%ZZ");
assert.equal(queryString.parse(queryString.stringify({ q: "a+b / café" })).q, "a+b / café");

// The vulnerable decoder repeatedly reprocessed malformed byte sequences.
// The parent test bounds execution in a subprocess so regressions cannot hang Jest.
const malformed = "%A0".repeat(1000);
assert.equal(queryString.parse(`q=${malformed}`).q, malformed);

const fromExpo = createRequire(require.resolve("expo/package.json"));
const fromMetro = createRequire(fromExpo.resolve("@expo/metro-config/package.json"));
const browserslist = fromMetro("browserslist");
assert.ok(browserslist(["last 1 chrome version"]).length > 0);
process.stdout.write("URL dependencies are compatible\n");
