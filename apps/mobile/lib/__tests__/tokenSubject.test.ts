import { tokenSubject } from "@/lib/tokenSubject";

function accessTokenFor(sub: unknown): string {
  const encode = (value: unknown) => btoa(JSON.stringify(value)).replace(/=/g, "").replace(/\+/g, "-").replace(/\//g, "_");
  return `${encode({ alg: "HS256", typ: "JWT" })}.${encode({ sub })}.signature`;
}

it("reads the account id inside an access token", () => {
  expect(tokenSubject(accessTokenFor("user-1"))).toBe("user-1");
});

it.each(["opaque-token", "a.@@.b", "a.bnVsbA.b", "a.e30.b", "a.e30.", accessTokenFor(123)])(
  "is null for an unreadable or missing subject: %s", (token) => {
    expect(tokenSubject(token)).toBeNull();
  },
);
