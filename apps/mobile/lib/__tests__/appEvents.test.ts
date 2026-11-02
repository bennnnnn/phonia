import { emitAppEvent, onAppEvent } from "@/lib/appEvents";

it("tells each follower of an event, and only that event's", () => {
  const deleted = jest.fn();
  const added = jest.fn();
  const stopDeleted = onAppEvent("chatsDeleted", deleted);
  const stopAdded = onAppEvent("attachmentAdded", added);
  emitAppEvent("chatsDeleted", { chatIds: ["c1", "c2"] });
  expect(deleted).toHaveBeenCalledWith({ chatIds: ["c1", "c2"] });
  expect(added).not.toHaveBeenCalled();
  stopDeleted();
  stopAdded();
});

it("stops telling a follower that stopped", () => {
  const follower = jest.fn();
  const stop = onAppEvent("memoryChanged", follower);
  stop();
  emitAppEvent("memoryChanged", {});
  expect(follower).not.toHaveBeenCalled();
});

it("keeps telling the others when one follower throws", () => {
  const after = jest.fn();
  const stopBroken = onAppEvent("attachmentDeleted", () => {
    throw new Error("broken follower");
  });
  const stopAfter = onAppEvent("attachmentDeleted", after);
  expect(() => emitAppEvent("attachmentDeleted", { attachmentId: "a", chatId: null })).not.toThrow();
  expect(after).toHaveBeenCalledTimes(1);
  stopBroken();
  stopAfter();
});
