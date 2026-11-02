import {
  isRequestId,
  newRequestId,
  REQUEST_ID_HEADER,
  responseRequestId,
  withRequestId,
} from "@/lib/api/requestId";

describe("request ids", () => {
  it("makes ids the API accepts, and a new one each call", () => {
    const ids = new Set(Array.from({ length: 200 }, newRequestId));
    expect(ids.size).toBe(200);
    for (const id of ids) expect(id).toMatch(/^[A-Za-z0-9_-]{1,64}$/);
  });

  it("puts a socket's id in its query, beside what is there", () => {
    expect(withRequestId("wss://api.test/ws/chats/1", "abc-1")).toBe(
      "wss://api.test/ws/chats/1?request_id=abc-1",
    );
    expect(withRequestId("wss://api.test/ws?x=1#frag", "abc-1")).toBe(
      "wss://api.test/ws?x=1&request_id=abc-1#frag",
    );
  });

  it("reads the API's echo only when it is an id", () => {
    const echo = (value: string | null) =>
      ({ headers: { get: (name: string) => (name === REQUEST_ID_HEADER ? value : null) } }) as unknown as Response;
    expect(responseRequestId(echo("abc-123_x"))).toBe("abc-123_x");
    expect(responseRequestId(echo("bad id\nline"))).toBeNull();
    expect(responseRequestId(echo(null))).toBeNull();
    expect(responseRequestId({} as Response)).toBeNull();
    expect(isRequestId("x".repeat(65))).toBe(false);
  });
});
