/**
 * Structural guard: a catch that drops its error may only grow rarer.
 *
 * These throw the failure away: nothing reaches Sentry or the console, and the screen
 * quietly does something else.
 * - a `catch {}` with no statement that does anything: empty, a comment, `;`, `{}`, a name
 *   or `void 0` on its own, `continue`/`break`, or a `return` of nothing (`return;`,
 *   `return undefined`, `return void 0`);
 * - a promise rejection handler (`.catch(h)`, `["catch"](h)`, or the second argument of
 *   `.then(ok, h)`) that does nothing in the same sense: `() => {}`, `() => undefined`,
 *   `(_e) => void 0`, `noop`, or a function that does nothing, declared in the file or
 *   imported from another (through barrels too).
 * Doing something is a call, an assignment, a throw, or a `return` of a value: a handler
 * that returns a value, even `() => null`, is not counted here. When it does not report
 * the error either, `swallowedCatches.test.ts` counts it.
 *
 * Today's are counted per file in `emptyCatchBaseline.json`; no file may gain one. Report
 * the error (`lib/sentry.ts`, a warning) or hand it on. After removing one, rerun with
 * `UPDATE_EMPTY_CATCHES=1` to lower the count.
 */
import * as ts from "typescript";

import { catchCounts, emptyCatches, type Resolve } from "./support/catches";
import { compareWithBaseline, recordedBaseline } from "./support/ratchet";

declare const __dirname: string;

const BASELINE = `${__dirname}/emptyCatchBaseline.json`;

describe("empty catches", () => {
  const counts = catchCounts(emptyCatches);
  const { added, grown, lower } = compareWithBaseline(
    counts,
    recordedBaseline(BASELINE, counts, "UPDATE_EMPTY_CATCHES"),
  );
  const parse = (lines: string[], name = "x.ts"): ts.SourceFile =>
    ts.createSourceFile(name, lines.join("\n"), ts.ScriptTarget.Latest, true);

  it("counts only catches that drop the error", () => {
    const dropped = [
      "try { a(); } catch {}",
      "try { a(); } catch (error) { /* ignored */ }",
      "load().catch(() => {});",
      "load().catch(async () => {});",
      "load().catch(function () {});",
      "load().catch(() => undefined);",
      "load().catch((_e) => void 0);",
      "load().catch(() => { return; });",
      "load().catch(noop);",
      "load().catch(_.noop);",
      "load().then(show, () => {});",
      "const ignore = () => undefined; load().catch(ignore);",
      // 2026-11-01: catches that did nothing in other words dropped their errors unseen.
      "function f() { try { a(); } catch { return; } }",
      "function f() { try { a(); } catch (error) { ; } }",
      "load().catch(() => { ; });",
      "try { a(); } catch { void 0; }",
      "try { a(); } catch { {} }",
      "function f() { try { a(); } catch { return void 0; } }",
      "function f(): string | undefined { try { return a(); } catch { return undefined; } }",
      "try { a(); } catch (e) { e; }",
      "for (const x of xs) { try { a(x); } catch { continue; } }",
      "for (const x of xs) { try { a(x); } catch { if (x) break; } }",
      "load().catch(() => { {} });",
      'load()["catch"](() => {});',
      "load().catch(function quiet() { return undefined; });",
    ];
    const kept = [
      "try { a(); } catch (error) { captureException(error); }",
      "try { a(); } catch { return null; }",
      "function f() { try { a(); } catch { return false; } }",
      "try { a(); } catch (e) { last = e; }",
      "try { a(); } catch { failures += 1; }",
      "try { a(); } catch { void report(); }",
      "try { a(); } catch (e) { throw e; }",
      "load().catch((error) => report(error));",
      'load()["catch"]((error) => report(error));',
      "load().catch(report);",
      "load().catch(() => null);",
      "load().catch((e) => e);",
      "load().then(show);",
      "load().then(() => {});",
    ];
    for (const line of dropped) expect([line, emptyCatches(parse([line]))]).toEqual([line, 1]);
    for (const line of kept) expect([line, emptyCatches(parse([line]))]).toEqual([line, 0]);
  });

  it("reads a do-nothing handler imported from another file, through a barrel", () => {
    const files = new Map([
      ["./quiet", parse(["export const ignore = () => {};", "export function report(e: unknown) { log(e); }"], "/app/lib/quiet.ts")],
      ["@/lib", parse(['export { ignore as skip, report } from "./quiet";'], "/app/lib/index.ts")],
    ]);
    const resolve: Resolve = (specifier) => files.get(specifier);
    const user = parse([
      'import { skip as hush, report } from "@/lib";',
      "load().catch(hush);",
      "load().catch(report);",
    ], "/app/features/x.ts");
    expect(emptyCatches(user, resolve)).toBe(1);
  });

  it("lets no file gain one", () => {
    // Report the error or hand it on, instead of recording it.
    expect({ added, grown }).toEqual({ added: [], grown: [] });
  });

  it("records the current counts", () => {
    // Fewer now: rerun with UPDATE_EMPTY_CATCHES=1 to lock it in.
    expect(lower).toEqual([]);
  });
});
