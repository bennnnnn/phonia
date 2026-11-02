import {
  resetComposerDraftsForAccount,
  resetComposerDraftResetListeners,
  subscribeComposerDraftReset,
} from "@/features/chat/model/composerDraftReset";

describe("composerDraftReset", () => {
  afterEach(() => {
    resetComposerDraftResetListeners();
  });

  it("notifies the mounted composer so sign-out can wipe drafts", () => {
    const listener = jest.fn();
    const unsubscribe = subscribeComposerDraftReset(listener);
    resetComposerDraftsForAccount();
    expect(listener).toHaveBeenCalledTimes(1);
    unsubscribe();
    resetComposerDraftsForAccount();
    expect(listener).toHaveBeenCalledTimes(1);
  });
});
