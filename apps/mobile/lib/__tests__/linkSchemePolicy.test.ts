import { Linking } from "react-native";

import { isAllowedLinkUrl, openAllowedUrl } from "@/lib/linkSchemePolicy";

jest.mock("react-native", () => ({
  Linking: {
    openURL: jest.fn(),
  },
}));

describe("isAllowedLinkUrl", () => {
  it("allows http(s), mailto, tel, sms, maps, geo schemes", () => {
    expect(isAllowedLinkUrl("https://example.com/path")).toBe(true);
    expect(isAllowedLinkUrl("http://example.com/path")).toBe(true);
    expect(isAllowedLinkUrl("mailto:user@example.com")).toBe(true);
    expect(isAllowedLinkUrl("tel:+15551234567")).toBe(true);
    expect(isAllowedLinkUrl("sms:+15551234567")).toBe(true);
    expect(isAllowedLinkUrl("maps://?q=coffee")).toBe(true);
    expect(isAllowedLinkUrl("geo:37.7749,-122.4194")).toBe(true);
  });

  it("blocks javascript: and data: schemes (script execution vectors)", () => {
    expect(isAllowedLinkUrl("javascript:alert(1)")).toBe(false);
    expect(isAllowedLinkUrl("javascript:fetch('https://evil/steal')")).toBe(false);
    expect(isAllowedLinkUrl("data:text/html,<script>alert(1)</script>")).toBe(false);
    expect(isAllowedLinkUrl("data:text/html;base64,PHNjcmlwdD4=")).toBe(false);
  });

  it("blocks file: and content: schemes (local-file access)", () => {
    expect(isAllowedLinkUrl("file:///etc/passwd")).toBe(false);
    expect(isAllowedLinkUrl("content://media/external/images/1")).toBe(false);
  });

  it("blocks ws: and other non-allowlisted schemes", () => {
    expect(isAllowedLinkUrl("ws://evil.example.com/exfil")).toBe(false);
    expect(isAllowedLinkUrl("vbscript:msgbox(1)")).toBe(false);
    expect(isAllowedLinkUrl("ftp://example.com/file")).toBe(false);
  });

  it("blocks empty / malformed / bare / relative inputs", () => {
    expect(isAllowedLinkUrl(undefined)).toBe(false);
    expect(isAllowedLinkUrl(null)).toBe(false);
    expect(isAllowedLinkUrl("")).toBe(false);
    expect(isAllowedLinkUrl("   ")).toBe(false);
    expect(isAllowedLinkUrl("not-a-url")).toBe(false);
    expect(isAllowedLinkUrl("/local/path")).toBe(false);
    expect(isAllowedLinkUrl("../relative")).toBe(false);
  });

  it("is case-insensitive on scheme", () => {
    expect(isAllowedLinkUrl("HTTPS://example.com")).toBe(true);
    expect(isAllowedLinkUrl("MAILTO:user@example.com")).toBe(true);
    expect(isAllowedLinkUrl("JavaScript:alert(1)")).toBe(false);
  });
});

describe("openAllowedUrl", () => {
  beforeEach(() => {
    jest.clearAllMocks();
    (Linking.openURL as jest.Mock).mockResolvedValue(undefined);
  });

  it("opens allowlisted http(s) URLs", async () => {
    await expect(openAllowedUrl("https://example.com")).resolves.toBe(true);
    expect(Linking.openURL).toHaveBeenCalledWith("https://example.com");
  });

  it("does not open javascript: or data: URLs", async () => {
    await expect(openAllowedUrl("javascript:alert(1)")).resolves.toBe(false);
    await expect(openAllowedUrl("data:text/html,<script>alert(1)</script>")).resolves.toBe(
      false,
    );
    expect(Linking.openURL).not.toHaveBeenCalled();
  });

  it("returns false when Linking.openURL rejects", async () => {
    (Linking.openURL as jest.Mock).mockRejectedValueOnce(new Error("no handler"));
    await expect(openAllowedUrl("https://example.com")).resolves.toBe(false);
  });
});
