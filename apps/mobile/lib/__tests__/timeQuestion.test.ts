import { assistantReplyIsTimeAnswer, extractClockTimezone, isIanaTimezoneOnly } from "@/lib/timeQuestion";

/**
 * The server's whole reply to a local "what time is it?" (`format_time_answer`
 * in apps/api/app/services/time_context.py). The server decides the question;
 * the phone only reads the reply.
 */
const SERVER_TIME_ANSWER = "```clock\n```";

describe("assistantReplyIsTimeAnswer", () => {
  it("reads the server's local time answer as a time answer", () => {
    expect(assistantReplyIsTimeAnswer(SERVER_TIME_ANSWER)).toBe(true);
    expect(extractClockTimezone(SERVER_TIME_ANSWER)).toBe("");
  });

  it.each([
    ["pinned to another city's timezone", "```clock\nAmerica/New_York\n```"],
    ["after a line of prose", "Here you go:\n\n```clock\n```"],
    ["holding a reading", "```clock\n3:04 PM\n```"],
  ])("treats a clock fence %s as a time answer", (_label, reply) => {
    expect(assistantReplyIsTimeAnswer(reply)).toBe(true);
  });

  it("keeps the timezone a city answer pinned", () => {
    expect(extractClockTimezone("```clock\nAmerica/New_York\n```")).toBe("America/New_York");
  });

  it.each([
    ["a 12-hour reading", "```\n3:04 PM\n```"],
    ["a bold 24-hour reading", "```text\n**14:32:05**\n```"],
    ["a timezone", "```\nAsia/Tokyo\n```"],
  ])("treats a fence holding only %s as a time answer", (_label, reply) => {
    expect(assistantReplyIsTimeAnswer(reply)).toBe(true);
  });

  it.each([
    ["prose", "pineapple"],
    ["prose with a clock time in it", "Your meeting is at 3:00 PM."],
    ["the shown-clock reading", "Friday, October 16, 2026, 3:04:05 PM EDT."],
    ["inline code naming the fence", "Use a `clock` fence for that."],
    ["a code fence", "```python\nprint(time.time())\n```"],
    ["an empty code fence", "```python\n```"],
    ["a code fence whose first word is clock", "```\nclock speed: 3.2 GHz\n```"],
  ])("does not treat %s as a time answer", (_label, reply) => {
    expect(assistantReplyIsTimeAnswer(reply)).toBe(false);
  });
});

describe("isIanaTimezoneOnly", () => {
  it.each(["America/New_York", "America/Argentina/Buenos_Aires", "Etc/GMT+5", "Asia/Tokyo"])(
    "reads %s as a timezone",
    (zone) => {
      expect(isIanaTimezoneOnly(zone)).toBe(true);
    },
  );

  it.each(["TCP/IP", "and/or", "input/output", "km/h"])("does not read %s as a timezone", (text) => {
    expect(isIanaTimezoneOnly(text)).toBe(false);
    expect(assistantReplyIsTimeAnswer("```\n" + text + "\n```")).toBe(false);
  });
});
