import { isAbortError } from "@/lib/api/abort";

it("detects a cancel with or without a DOMException global", () => {
  expect(isAbortError(new DOMException("Aborted", "AbortError"))).toBe(true);
  const err = new Error("Aborted");
  err.name = "AbortError";
  expect(isAbortError(err)).toBe(true);
  const canceled = new Error("canceled");
  canceled.name = "CanceledError";
  expect(isAbortError(canceled)).toBe(true);
  expect(isAbortError(new Error("network"))).toBe(false);
  expect(isAbortError(null)).toBe(false);
  expect(isAbortError("AbortError")).toBe(false);
  const domException = globalThis.DOMException;
  Object.defineProperty(globalThis, "DOMException", { value: undefined, configurable: true });
  try {
    expect(isAbortError(err)).toBe(true);
    expect(isAbortError({ name: "something-else" })).toBe(false);
  } finally {
    Object.defineProperty(globalThis, "DOMException", { value: domException, configurable: true });
  }
});
