/**
 * Structural guard: a catch that does something but drops the error may only grow rarer.
 *
 * `emptyCatches.test.ts` counts catches that do nothing. These do something, return a
 * default, set a flag, show a toast, and still throw the failure away: nothing reaches
 * Sentry or a log, and nothing reads the error, so a send, an upload or a purchase that
 * failed on a phone left no trace (outside review, 2026-11-01).
 * - a `catch` clause whose block does something and neither names its error, throws, nor
 *   calls a reporter;
 * - a rejection handler written in place (`.catch(() => null)`, `.then(ok, () => …)`)
 *   that does the same. A handler named by reference (`.catch(reject)`) is handed the
 *   error and is not counted.
 * A reporter is `console.*`, Sentry's `captureException`/`captureMessage`, or anything
 * imported from `lib/sentry.ts` or the Sentry SDK. A catch that does nothing at all is
 * `emptyCatches.test.ts`'s and is not counted again here.
 *
 * Today's are counted per file in `swallowedCatchBaseline.json`; no file may gain one.
 * Report it through `lib/sentry.ts` (`reportFailure`, metadata only), or read the error to
 * decide what it means. After removing one, rerun with `UPDATE_SWALLOWED_CATCHES=1` to
 * lower the count.
 */
import * as ts from "typescript";

import { catchCounts, swallowedCatches, swallowedCatchLines, type Resolve } from "./support/catches";
import { compareWithBaseline, recordedBaseline } from "./support/ratchet";

declare const __dirname: string;

const BASELINE = `${__dirname}/swallowedCatchBaseline.json`;

describe("swallowed catches", () => {
  const counts = catchCounts(swallowedCatches);
  const { added, grown, lower } = compareWithBaseline(
    counts,
    recordedBaseline(BASELINE, counts, "UPDATE_SWALLOWED_CATCHES"),
  );
  const parse = (lines: string[], name = "x.ts"): ts.SourceFile =>
    ts.createSourceFile(name, lines.join("\n"), ts.ScriptTarget.Latest, true);
  const count = (line: string, resolve?: Resolve) => swallowedCatches(parse([line]), resolve);

  it("counts catches that act but drop the error", () => {
    const swallowed = [
      "function f() { try { return a(); } catch { return null; } }",
      "function f() { try { return a(); } catch (error) { return false; } }",
      "try { a(); } catch { setLoading(false); }",
      "try { a(); } catch { failures += 1; }",
      "try { a(); } catch { feedback.error(t('x')); }",
      "try { a(); } catch (_error) { showBanner(); }",
      "load().catch(() => null);",
      "load().catch(() => setFailed(true));",
      "load().catch(async () => { await retry(); });",
      "load().catch(function () { return []; });",
      "load().then(show, () => fallback());",
      'load()["catch"](() => null);',
      // A throw in a function the catch hands on is not this catch's.
      "try { a(); } catch { later(() => { throw new Error('x'); }); }",
    ];
    const seen = [
      "try { a(); } catch (error) { captureException(error); }",
      "try { a(); } catch (error) { report(error); return null; }",
      "try { a(); } catch (e) { if (isAbortError(e)) return null; throw e; }",
      "try { a(); } catch { throw new Error('wrapped'); }",
      "try { a(); } catch (e) { last = e; }",
      "try { a(); } catch ({ code }) { return code === 404; }",
      "try { a(); } catch { console.warn('a failed'); return null; }",
      "try { a(); } catch { Sentry.captureMessage('a failed'); }",
      "load().catch((error) => report(error));",
      "load().catch((error) => { setError(error); });",
      "load().catch(report);",
      "load().catch(reject);",
      "load().then(show, (error) => fail(error));",
      "load().then(show);",
      "load().then(() => {});",
      // Doing nothing at all is the empty-catch guard's.
      "try { a(); } catch {}",
      "load().catch(() => {});",
      "function f() { try { a(); } catch { return; } }",
    ];
    for (const line of swallowed) expect([line, count(line)]).toEqual([line, 1]);
    for (const line of seen) expect([line, count(line)]).toEqual([line, 0]);
  });

  it("reads a reporter imported from lib/sentry.ts or the Sentry SDK", () => {
    const sentry = parse(["export function reportFailure(area: string, error: unknown) {}"], "/app/lib/sentry.ts");
    const resolve: Resolve = (specifier) => (specifier === "@/lib/sentry" ? sentry : undefined);
    const user = parse([
      'import { reportFailure as tell } from "@/lib/sentry";',
      'import * as Sentry from "@sentry/react-native";',
      'import type { FailureArea } from "@/lib/types";',
      "try { a(); } catch { tell('chat_load', null); return null; }",
      "try { a(); } catch { Sentry.addBreadcrumb({}); return null; }",
      "load().catch(() => { tell('purchase', null); return null; });",
      "try { a(); } catch { FailureArea(); return null; }",
    ], "/app/features/x.ts");
    expect(swallowedCatchLines(user, resolve)).toEqual([7]);
  });

  it("lets no file gain one", () => {
    // Report the error (lib/sentry.ts) or read it, instead of recording it.
    expect({ added, grown }).toEqual({ added: [], grown: [] });
  });

  it("records the current counts", () => {
    // Fewer now: rerun with UPDATE_SWALLOWED_CATCHES=1 to lock it in.
    expect(lower).toEqual([]);
  });
});
