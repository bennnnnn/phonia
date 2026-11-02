import { ApiRequestError } from "@/lib/api/errorBody";
import { abortError, isServerUnreachable, serverUnreachableError } from "@/lib/api/deadline";

// A screen words these by kind, never by their English (a Library toast, a picture card).
it.each<[string, unknown, boolean]>([
  ["past a deadline", serverUnreachableError(), true],
  ["React Native offline", new TypeError("Network request failed"), true],
  ["a browser offline", new TypeError("Failed to fetch"), true],
  ["a timeout's abort", abortError(), true],
  ["a refusal the API answered", new ApiRequestError(503, JSON.stringify({ detail: "Network error" })), false],
  ["a failure on the phone", new Error("Could not open this attachment."), false],
  ["not an error", "Network request failed", false],
])("tells whether Recall gave no answer: %s", (_label, error, unreachable) => {
  expect(isServerUnreachable(error)).toBe(unreachable);
});
