import { deriveAssistantMessageContent } from "@/lib/markdown/assistantMessageContent";

describe("deriveAssistantMessageContent", () => {
  const base = {
    content: "Hello **world**",
    layoutFrozen: false,
    isUser: false,
    priorUserText: null,
    messageId: "msg-1",
    isGenerating: false,
  };

  it("leaves streaming mode after the settle hold, including a final line without newline", () => {
    for (const content of ["> Tip: Save a copy.", "12+3=15"]) {
      expect(deriveAssistantMessageContent({ ...base, content, isGenerating: true }).markdownStreamMode).toBe(true);
      const finished = deriveAssistantMessageContent({ ...base, content });
      expect(finished.markdownStreamMode).toBe(false);
      expect(finished).toEqual(deriveAssistantMessageContent({ ...base, content }));
    }
  });

  it("returns empty markdown flags for user rows", () => {
    const result = deriveAssistantMessageContent({
      ...base,
      isUser: true,
    });

    expect(result.showActionSlot).toBe(false);
    expect(result.showSearchSources).toBe(false);
    expect(result.markdownContent).toBe("Hello **world**");
  });

  it("defers rich chrome while layout is frozen", () => {
    const result = deriveAssistantMessageContent({
      ...base,
      content: "Answer with ```search_sources\n[]\n```",
      layoutFrozen: true,
    });

    expect(result.showSearchSources).toBe(false);
    expect(result.markdownStreamMode).toBe(true);
  });

  it("shows actions as soon as generation finishes (even mid layout settle)", () => {
    const ready = deriveAssistantMessageContent({
      ...base,
      isGenerating: false,
    });
    const streaming = deriveAssistantMessageContent({
      ...base,
      isGenerating: true,
    });
    const settling = deriveAssistantMessageContent({
      ...base,
      isGenerating: false,
      layoutFrozen: true,
    });

    expect(ready.actionsReady).toBe(true);
    expect(streaming.actionsReady).toBe(false);
    // Icons mount at stream end; composer-gap pad (not a hidden slot) holds
    // the height so the layout-settle freeze cannot shift the prose.
    expect(settling.actionsReady).toBe(true);
  });

  it("builds markdown reset key from renderKey and content length", () => {
    const result = deriveAssistantMessageContent({
      ...base,
      renderKey: "stream-42",
      content: "Hi",
    });

    expect(result.markdownResetKey).toBe("stream-42:2");
  });

  it("parses assistant image markers and strips them from markdown", () => {
    const attachmentId = "11111111-1111-1111-1111-111111111111";
    const result = deriveAssistantMessageContent({
      ...base,
      content: `[Image: /attachments/${attachmentId}/file]`,
    });

    expect(result.showImages).toBe(true);
    expect(result.images).toHaveLength(1);
    expect(result.images[0]?.attachmentId).toBe(attachmentId);
    expect(result.markdownContent).toBe("");
    expect(result.hasMarkdown).toBe(false);
  });

  it("hides leftover lookup Source captions under photos", () => {
    const attachmentId = "11111111-1111-1111-1111-111111111111";
    const result = deriveAssistantMessageContent({
      ...base,
      content: `[Image: /attachments/${attachmentId}/file]\n\nSource: Car - Wikipedia`,
    });

    expect(result.showImages).toBe(true);
    expect(result.images).toHaveLength(1);
    expect(result.markdownContent).toBe("");
    expect(result.hasMarkdown).toBe(false);
  });

  it("reads a reply's sources fence only once its layout settles", () => {
    const content = 'Answer.\n\n```sources\n[{"title":"AP","url":"https://apnews.com/a"}]\n```';
    const frozen = deriveAssistantMessageContent({ ...base, content, layoutFrozen: true });
    expect(frozen.searchSources).toEqual([]);
    // Flush to flush, the same empty list: nothing under the reply is told to redraw.
    expect(deriveAssistantMessageContent({ ...base, content: `${content}\n`, layoutFrozen: true }).searchSources)
      .toBe(frozen.searchSources);

    const attached = [{ title: "DC", url: "https://example.com/dc" }];
    expect(
      deriveAssistantMessageContent({ ...base, content, layoutFrozen: true, liveSearchSources: attached })
        .searchSources,
    ).toBe(attached);

    const settled = deriveAssistantMessageContent({ ...base, content });
    expect(settled.searchSources).toEqual([{ title: "AP", url: "https://apnews.com/a" }]);
    expect(settled.markdownContent).toBe("Answer.");
  });

  it("hides Sources under a live clock even when search hits are attached", () => {
    const result = deriveAssistantMessageContent({
      ...base,
      priorUserText: "What time is it in dc",
      content: "```clock\nAmerica/New_York\n```",
      liveSearchSources: [
        { title: "DC time", url: "https://example.com/dc" },
      ],
    });

    expect(result.showLiveClock).toBe(true);
    expect(result.searchSources).toHaveLength(1);
    expect(result.showSearchSources).toBe(false);
  });

  it("shows the live clock for the server's time answer, whatever the ask's punctuation", () => {
    const result = deriveAssistantMessageContent({
      ...base,
      priorUserText: "What’s the time?",
      content: "```clock\n```",
    });

    expect(result.showLiveClock).toBe(true);
    expect(result.clockTimezone).toBe("");
    expect(result.markdownContent).toBe("");
  });

  it("keeps a contextual follow-up's prose without injecting a clock", () => {
    const result = deriveAssistantMessageContent({
      ...base,
      priorUserText: "Again",
      content: "pineapple",
    });

    expect(result.showLiveClock).toBe(false);
    expect(result.markdownContent).toBe("pineapple");
  });

  it("hides Sources on a where-am-I reply even when search hits leaked", () => {
    const result = deriveAssistantMessageContent({
      ...base,
      priorUserText: "Where am iI",
      content: "You're in **San Francisco, CA**.",
      liveSearchSources: [
        { title: "Los Baños", url: "https://example.com/lb" },
      ],
    });

    expect(result.searchSources).toHaveLength(1);
    expect(result.showSearchSources).toBe(false);
  });

  it("keeps ordinary multiple-choice prose in the reply", () => {
    const result = deriveAssistantMessageContent({
      ...base,
      content: [
        "**ephemeral**",
        "",
        "What does it mean?",
        "",
        "A) lasting forever",
        "B) very loud",
        "C) related to water",
        "D) lasting a short time",
        "",
        "Reply with A, B, C, or D.",
      ].join("\n"),
    });

    expect(result.markdownContent).toContain("A) lasting forever");
    expect(result.markdownContent).toContain("Reply with A, B, C, or D.");
  });

  it("strips leftover vocab_quiz fences from stored replies", () => {
    const result = deriveAssistantMessageContent({
      ...base,
      content: [
        "Let's check this word.",
        "",
        "```vocab_quiz",
        JSON.stringify({
          word: "hola",
          question: "What does hola mean?",
          correct: "A",
          choices: [
            { letter: "A", text: "hello" },
            { letter: "B", text: "goodbye" },
            { letter: "C", text: "please" },
            { letter: "D", text: "thanks" },
          ],
        }),
        "```",
      ].join("\n"),
    });

    expect(result.markdownContent).not.toContain("vocab_quiz");
    expect(result.markdownContent).not.toContain("What does hola mean?");
  });

  it("strips leftover job-results fences from stored replies", () => {
    const result = deriveAssistantMessageContent({
      ...base,
      content: ["Here are matches.", "", "```job-results", "{\"matches\":[]}", "```"].join("\n"),
    });

    expect(result.markdownContent).not.toContain("job-results");
    expect(result.markdownContent).toContain("Here are matches.");
  });

  it("drops the unverified footer from a stored reply", () => {
    const result = deriveAssistantMessageContent({
      ...base,
      content: [
        "The bakery pickup is at 07:00 and the concert is at 19:00.",
        "",
        "*I couldn't automatically verify this result.*",
      ].join("\n"),
    });

    expect(result.markdownContent).toBe(
      "The bakery pickup is at 07:00 and the concert is at 19:00.",
    );
    expect(result.markdownContent).not.toContain("automatically verify");
  });

  it("strips vocab_card fences instead of rendering a study card in chat", () => {
    const result = deriveAssistantMessageContent({
      ...base,
      content: [
        "Write your own sentence using **effervescent**.",
        "",
        "```vocab_card",
        JSON.stringify({
          word: "effervescent",
          definition: "bubbly and lively",
          example_sentence: "Her effervescent laughter filled the room.",
        }),
        "```",
      ].join("\n"),
    });

    expect(result.markdownContent).toContain("Write your own sentence");
    expect(result.markdownContent).not.toContain("vocab_card");
  });

  it("strips settings_proposal fences and exposes the card payload", () => {
    const result = deriveAssistantMessageContent({
      ...base,
      content: [
        "I can switch that for you: Appearance → Dark.",
        "```settings_proposal",
        '{"proposal_id":"abc","changes":[{"field":"appearance","value":"dark","label":"Dark"}]}',
        "```",
      ].join("\n"),
    });

    expect(result.showSettingsProposals).toBe(true);
    expect(result.settingsProposals[0]?.proposal_id).toBe("abc");
    expect(result.markdownContent).toBe("I can switch that for you: Appearance → Dark.");
  });

  it("strips leftover learning_launch fences from stored replies", () => {
    const projectId = "11111111-1111-4111-8111-111111111111";
    const result = deriveAssistantMessageContent({
      ...base,
      content: [
        "You have 3/10 Spanish words today.",
        "```learning_launch",
        JSON.stringify({ project_id: projectId, action: "continue" }),
        "```",
      ].join("\n"),
    });

    expect(result.markdownContent).toContain("3/10 Spanish");
    expect(result.markdownContent).not.toContain("learning_launch");
    expect(result.markdownContent).not.toContain(projectId);
    expect("learningLaunch" in result).toBe(false);
  });
});
