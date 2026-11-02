import {
  buildGmailAppComposeUrl,
  buildGmailComposeUrl,
  fullEmailText,
  gmailComposeCandidates,
} from "@/features/drafts/model/emailCompose";

describe("emailCompose", () => {
  const draft = {
    to: "wife@example.com",
    subject: "Thinking of You",
    body: "My love,\n\nJust thinking of you.",
  };

  it("builds full copy text", () => {
    expect(fullEmailText(draft)).toContain("To: wife@example.com");
    expect(fullEmailText(draft)).toContain("Subject: Thinking of You");
    expect(fullEmailText(draft)).toContain("My love,");
  });

  it("builds gmail web compose url", () => {
    const url = buildGmailComposeUrl(draft);
    expect(url).toContain("mail.google.com");
    expect(url).toContain("to=wife%40example.com");
    expect(url).toContain("su=Thinking+of+You");
  });

  it("builds gmail app compose url", () => {
    const url = buildGmailAppComposeUrl(draft);
    expect(url).toContain("googlegmail:///co");
    expect(url).toContain("subject=Thinking+of+You");
  });

  it("orders app before web", () => {
    const urls = gmailComposeCandidates(draft);
    expect(urls[0]).toContain("googlegmail");
    expect(urls[1]).toContain("mail.google.com");
  });
});
