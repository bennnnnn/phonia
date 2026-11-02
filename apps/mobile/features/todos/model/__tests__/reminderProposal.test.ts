import {
  isProposalSaved,
  markProposalSaved,
  parseReminderProposals,
  proposalAction,
  stripReminderProposalFences,
} from "@/features/todos/model/reminderProposal";
import { stripReminderFences } from "@/features/todos/model/reminderFence";
import { deriveAssistantMessageContent } from "@/lib/markdown/assistantMessageContent";

const card = (body: object) => "```reminder_proposal\n" + JSON.stringify(body) + "\n```";
const ADD = {
  proposal_id: "p1",
  items: [
    {
      action: "add",
      title: "Call mom",
      due_at: "2026-10-15T18:00:00Z",
      repeat: "daily",
      when: "Thursday, Oct 15, 6:00 PM · daily",
    },
  ],
};

describe("parseReminderProposals", () => {
  it("reads the card's id and items", () => {
    expect(parseReminderProposals(`Sure.\n\n${card(ADD)}`)).toEqual([
      {
        proposalId: "p1",
        saved: false,
        timeZone: null,
        items: [
          {
            action: "add",
            title: "Call mom",
            dueAt: "2026-10-15T18:00:00Z",
            repeat: "daily",
            topic: null,
            when: "Thursday, Oct 15, 6:00 PM · daily",
          },
        ],
      },
    ]);
  });

  it("reads a card the server marked saved", () => {
    const [proposal] = parseReminderProposals(card({ ...ADD, status: "saved" }));
    expect(proposal?.saved).toBe(true);
  });

  it("reads the zone the card's times were read in", () => {
    const [proposal] = parseReminderProposals(card({ ...ADD, tz: "Africa/Nairobi" }));
    expect(proposal?.timeZone).toBe("Africa/Nairobi");
  });

  it.each([
    ["broken JSON", "```reminder_proposal\n{\"proposal_id\": \n```"],
    ["no id", card({ items: ADD.items })],
    ["no usable item", card({ proposal_id: "p", items: [{ action: "explode", title: "x" }] })],
    ["an item without a title", card({ proposal_id: "p", items: [{ action: "add" }] })],
  ])("drops %s", (_name, content) => {
    expect(parseReminderProposals(content)).toEqual([]);
  });

  it("drops a repeat it does not know", () => {
    const [proposal] = parseReminderProposals(
      card({ proposal_id: "p", items: [{ action: "add", title: "Gym", repeat: "hourly" }] }),
    );
    expect(proposal?.items[0]?.repeat).toBeNull();
  });
});

describe("stripReminderProposalFences", () => {
  it("leaves the reply's words and drops the card", () => {
    expect(stripReminderProposalFences(`Sure.\n\n${card(ADD)}`)).toBe("Sure.");
  });

  it("is not touched by the plain reminder fence strip", () => {
    const content = `Sure.\n\n${card(ADD)}`;
    expect(stripReminderFences(content)).toBe(content);
  });
});

describe("proposalAction", () => {
  it("names one kind of change and says all for a mix", () => {
    const [one] = parseReminderProposals(card(ADD));
    expect(proposalAction(one!)).toBe("add");
    const [mixed] = parseReminderProposals(
      card({
        proposal_id: "p2",
        items: [
          { action: "complete", title: "Gym" },
          { action: "delete", title: "Rent" },
        ],
      }),
    );
    expect(proposalAction(mixed!)).toBe("all");
  });
});

describe("markProposalSaved", () => {
  it("keeps a card saved on this phone before the chat is refetched", () => {
    const [proposal] = parseReminderProposals(card({ ...ADD, proposal_id: "p-local" }));
    expect(isProposalSaved(proposal!)).toBe(false);
    markProposalSaved("p-local");
    expect(isProposalSaved(proposal!)).toBe(true);
  });
});

describe("deriveAssistantMessageContent reminder cards", () => {
  it("lifts the card out of the markdown", () => {
    const result = deriveAssistantMessageContent({
      content: `Sure.\n\n${card(ADD)}`,
      layoutFrozen: false,
      isUser: false,
      priorUserText: null,
      messageId: "m1",
      isGenerating: false,
    });
    expect(result.markdownContent).toBe("Sure.");
    expect(result.showReminderProposals).toBe(true);
    expect(result.reminderProposals[0]?.proposalId).toBe("p1");
  });
});
