import { ApiRequestError } from "@/lib/api/client";
import { scanFailureMessage } from "@/features/scanner/model/scanReadError";

jest.mock("@/lib/config", () => ({
  getApiUrl: () => "http://test.local",
}));
jest.mock("@/lib/auth", () => ({
  getSessionGeneration: () => 0,
  requireTokenSession: jest.fn(),
  SessionChangedError: class extends Error {},
  getRefreshToken: jest.fn(),
  setTokenPair: jest.fn(),
}));

const t = (key: string) => key;
const refused = (status: number, detail: unknown) =>
  new ApiRequestError(status, JSON.stringify({ detail }));

describe("scanFailureMessage", () => {
  it("words each coded refusal the phone's own way, whatever the English", () => {
    expect(scanFailureMessage(refused(429, { code: "scan_rate_limited", message: "Reworded." }), t)).toBe(
      "chat.scan_rate_limit",
    );
  });

  it("shows the server's words for another refusal of a named status", () => {
    expect(scanFailureMessage(refused(429, { code: "new_limit", message: "Slow down." }), t)).toBe(
      "Slow down.",
    );
  });

  // A Redis outage said "Too many scans in a row" (its 429), then "couldn't scan that photo".
  it("says Recall is down for an outage: the API's own 503, or a gateway's", () => {
    const down = refused(503, { code: "unavailable", message: "Service temporarily unavailable." });
    expect(scanFailureMessage(down, t)).toBe("common.service_unavailable");
    expect(scanFailureMessage(refused(502, "Bad Gateway"), t)).toBe("common.service_unavailable");
  });

  it("stays generic for anything else", () => {
    expect(scanFailureMessage(new Error("offline"), t)).toBeNull();
    expect(scanFailureMessage(refused(500, "nope"), t)).toBeNull();
    expect(scanFailureMessage(refused(400, { code: "invalid_image", message: "Bad" }), t)).toBeNull();
    expect(scanFailureMessage(refused(429, "  "), t)).toBeNull();
  });
});
