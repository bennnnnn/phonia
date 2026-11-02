import { imageHost, imageLoadPolicy } from "@/lib/images/imageUriPolicy";

jest.mock("@/lib/config", () => ({ getApiUrl: () => "https://api.recall.test" }));

describe("imageLoadPolicy", () => {
  it("loads the API's own images and inline pictures without asking", () => {
    expect(imageLoadPolicy("https://api.recall.test/attachments/abc/file")).toBe("load");
    expect(imageLoadPolicy("data:image/png;base64,iVBORw0KGgo=")).toBe("load");
    expect(imageLoadPolicy("data:image/jpeg;base64,/9j/4AAQ")).toBe("load");
    expect(imageLoadPolicy("blob:https://example.com/uuid")).toBe("load");
  });

  it("asks before loading any other https image: its URL can carry the user's data", () => {
    expect(imageLoadPolicy("https://upload.wikimedia.org/wikipedia/x.png")).toBe("ask");
    expect(imageLoadPolicy("https://evil.test/p.png?d=dentist-tuesday")).toBe("ask");
    expect(imageLoadPolicy("https://api.recall.test.evil.test/x.png")).toBe("ask");
    expect(imageLoadPolicy("https://api.recall.test:444/x.png")).toBe("ask");
  });

  it("blocks insecure, local-file, credentialed and script-capable sources", () => {
    expect(imageLoadPolicy("http://tracker.example.com/pixel.gif")).toBe("block");
    expect(imageLoadPolicy("file:///etc/passwd")).toBe("block");
    expect(imageLoadPolicy("content://media/external/images/1")).toBe("block");
    expect(imageLoadPolicy("ws://evil.example.com/exfil")).toBe("block");
    expect(imageLoadPolicy("javascript:alert(1)")).toBe("block");
    expect(imageLoadPolicy("data:image/svg+xml;base64,PHN2Zz4=")).toBe("block");
    expect(imageLoadPolicy("data:text/html,hi")).toBe("block");
    expect(imageLoadPolicy("https://user:pass@api.recall.test/x.png")).toBe("block");
  });

  it("blocks empty, malformed and relative inputs", () => {
    expect(imageLoadPolicy(undefined)).toBe("block");
    expect(imageLoadPolicy(null)).toBe("block");
    expect(imageLoadPolicy("")).toBe("block");
    expect(imageLoadPolicy("   ")).toBe("block");
    expect(imageLoadPolicy("not-a-url")).toBe("block");
    expect(imageLoadPolicy("/local/path.png")).toBe("block");
    expect(imageLoadPolicy("//evil.test/a.png")).toBe("block");
  });
});

describe("imageHost", () => {
  it("names the host a placeholder shows, in punycode", () => {
    expect(imageHost("https://Evil.Test/p.png?d=1")).toBe("evil.test");
    expect(imageHost("https://xn--pple-43d.com/x.png")).toBe("xn--pple-43d.com");
    expect(imageHost("https://аpple.com/x.png")).toBe("xn--pple-43d.com");
    expect(imageHost("nope")).toBe("");
  });
});
