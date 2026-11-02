import { proposalDueLabel } from "@/features/todos/model/proposalTime";
import { formatDate } from "@/lib/datetime/format";

// 9:00 AM in Nairobi, 2:00 AM in New York.
const DUE = new Date("2026-10-15T06:00:00Z");

describe("proposalDueLabel", () => {
  it("shows the card's own time and names its zone when the phone is elsewhere", () => {
    const label = proposalDueLabel(DUE, "Africa/Nairobi", "America/New_York");
    expect(label).toMatch(/^Thu, Oct 15, 9:00\sAM \S+/);
    expect(label).toMatch(/(GMT\+3|EAT)$/);
  });

  it("names no zone when the phone is in the card's zone", () => {
    expect(proposalDueLabel(DUE, "Africa/Nairobi", "Africa/Nairobi")).toMatch(
      /^Thu, Oct 15, 9:00\sAM$/,
    );
  });

  it("names no zone for another zone that shows the same time", () => {
    expect(proposalDueLabel(DUE, "Africa/Nairobi", "Africa/Addis_Ababa")).toMatch(
      /^Thu, Oct 15, 9:00\sAM$/,
    );
  });

  it.each([null, "Not/AZone"])("uses the user's zone for a card zone of %p", (zone) => {
    const label = proposalDueLabel(DUE, zone, "America/New_York");
    expect(label.endsWith(formatDate(DUE, "time"))).toBe(true);
  });
});
