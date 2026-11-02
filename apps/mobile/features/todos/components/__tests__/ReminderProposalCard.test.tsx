import { Linking } from "react-native";
import { fireEvent, render, waitFor } from "@testing-library/react-native";

import { ReminderProposalCard } from "@/features/todos/components/ReminderProposalCard";
import { parseReminderProposals } from "@/features/todos/model/reminderProposal";
import { api } from "@/lib/api";

const mockRefresh = jest.fn();

jest.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, options?: Record<string, string>) =>
      options?.topic ? `${key}:${options.topic}` : key,
  }),
}));
jest.mock("@/contexts/AuthContext", () => ({ useAuth: () => ({ token: "token" }) }));
jest.mock("@/features/todos/context/TodosContext", () => ({
  useTodosOptional: () => ({ refresh: mockRefresh }),
}));
jest.mock("@/lib/api", () => ({ api: { confirmReminderProposal: jest.fn() } }));
// The phone is in New York; times are drawn in its zone unless the card names another.
jest.mock("@/lib/datetime/phoneClock", () => ({
  readPhoneClock: () => ({ timeZone: "America/New_York", hourCycle: "h12" }),
}));
const mockAllowAlerts = jest.fn(async () => "on" as "on" | "off");
jest.mock("@/features/todos/model/reminderAlerts", () => ({
  allowReminderAlerts: () => mockAllowAlerts(),
}));

const confirm = api.confirmReminderProposal as jest.Mock;

function proposal(body: object) {
  const content = "```reminder_proposal\n" + JSON.stringify(body) + "\n```";
  return parseReminderProposals(content)[0]!;
}

const add = (id: string, extra: object = {}) =>
  proposal({
    proposal_id: id,
    items: [{ action: "add", title: "Call mom", due_at: "2026-10-15T18:00:00Z", ...extra }],
  });

describe("ReminderProposalCard", () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it("shows what will be saved and saves it on tap", async () => {
    confirm.mockResolvedValue({ items: [] });
    const view = await render(<ReminderProposalCard proposal={add("a1")} />);

    expect(view.getByText("Call mom")).toBeTruthy();
    expect(view.queryByText("todos.proposal_done_add")).toBeNull();
    await fireEvent.press(view.getByText("todos.proposal_add"));

    await waitFor(() => expect(view.getByText("todos.proposal_done_add")).toBeTruthy());
    expect(confirm).toHaveBeenCalledWith("token", "a1");
    expect(mockRefresh).toHaveBeenCalledWith({ silent: true, force: true });
    expect(view.queryByText("todos.proposal_add")).toBeNull();
  });

  it("says the alert is off, with a way to settings, when the user said no", async () => {
    confirm.mockResolvedValue({ items: [] });
    mockAllowAlerts.mockResolvedValueOnce("off");
    const openSettings = jest.spyOn(Linking, "openSettings").mockResolvedValue(undefined);
    const view = await render(<ReminderProposalCard proposal={add("off1")} />);
    await fireEvent.press(view.getByText("todos.proposal_add"));

    await waitFor(() => expect(view.getByText("todos.alerts_off")).toBeTruthy());
    expect(view.getByText("todos.proposal_done_add")).toBeTruthy();
    await fireEvent.press(view.getByText("todos.alerts_open_settings"));
    expect(openSettings).toHaveBeenCalled();
  });

  it("says nothing about alerts when they are on", async () => {
    confirm.mockResolvedValue({ items: [] });
    const view = await render(<ReminderProposalCard proposal={add("on1")} />);
    await fireEvent.press(view.getByText("todos.proposal_add"));
    await waitFor(() => expect(view.getByText("todos.proposal_done_add")).toBeTruthy());
    expect(mockAllowAlerts).toHaveBeenCalledTimes(1);
    expect(view.queryByText("todos.alerts_off")).toBeNull();
  });

  it("names a repeat beside the time", async () => {
    const view = await render(<ReminderProposalCard proposal={add("a2", { repeat: "weekly" })} />);
    expect(view.getByText(/todos\.repeat_weekly/)).toBeTruthy();
  });

  it("falls back to the server's wording when the time does not parse", async () => {
    const view = await render(
      <ReminderProposalCard
        proposal={add("a3", { due_at: "soon", when: "Thursday, Oct 15, 6:00 PM" })}
      />,
    );
    expect(view.getByText("Thursday, Oct 15, 6:00 PM")).toBeTruthy();
  });

  it("reads saved, with no button, once the server marked it", async () => {
    const view = await render(
      <ReminderProposalCard
        proposal={proposal({
          proposal_id: "a4",
          status: "saved",
          items: [{ action: "complete", title: "Gym" }],
        })}
      />,
    );
    expect(view.getByText("todos.proposal_done_complete")).toBeTruthy();
    expect(view.queryByText("todos.proposal_complete")).toBeNull();
  });

  it.each([
    [410, "todos.proposal_error_expired"],
    [409, "todos.proposal_error_changed"],
    [500, "todos.proposal_error_failed"],
  ])("says why a %s was not saved and keeps the button", async (status, message) => {
    confirm.mockRejectedValue(Object.assign(new Error("no"), { status }));
    const view = await render(<ReminderProposalCard proposal={add(`err-${status}`)} />);
    await fireEvent.press(view.getByText("todos.proposal_add"));
    await waitFor(() => expect(view.getByText(message)).toBeTruthy());
    expect(view.getByText("todos.proposal_add")).toBeTruthy();
    expect(mockRefresh).not.toHaveBeenCalled();
  });

  it("says where a move goes and labels a mix of changes as one save", async () => {
    const view = await render(
      <ReminderProposalCard
        proposal={proposal({
          proposal_id: "a5",
          items: [
            { action: "move", title: "Gym", topic: "Health" },
            { action: "delete", title: "Rent" },
          ],
        })}
      />,
    );
    expect(view.getByText("todos.proposal_to_list:Health")).toBeTruthy();
    expect(view.getByText("todos.proposal_all")).toBeTruthy();
  });

  it("shows the time the reply named, with its zone, when the phone is elsewhere", async () => {
    // F8.4: due 15:00Z read in Nairobi is 6:00 PM there, 11:00 AM on a New York phone.
    const view = await render(
      <ReminderProposalCard
        proposal={proposal({
          proposal_id: "tz1",
          tz: "Africa/Nairobi",
          items: [{ action: "add", title: "Call mom", due_at: "2026-10-15T15:00:00Z" }],
        })}
      />,
    );
    expect(view.getByText(/^Thu, Oct 15, 6:00\sPM (GMT\+3|EAT)$/)).toBeTruthy();
  });

  it("names no zone when the card's zone is the phone's", async () => {
    const view = await render(
      <ReminderProposalCard
        proposal={proposal({
          proposal_id: "tz2",
          tz: "America/New_York",
          items: [{ action: "add", title: "Call mom", due_at: "2026-10-15T15:00:00Z" }],
        })}
      />,
    );
    expect(view.getByText(/^Thu, Oct 15, 11:00\sAM$/)).toBeTruthy();
  });
});
