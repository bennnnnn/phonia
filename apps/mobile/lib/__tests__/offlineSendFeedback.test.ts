import { notifyOfflineSendBlocked } from "@/lib/offlineSendFeedback";

describe("notifyOfflineSendBlocked", () => {
  it("warns and invokes the toast callback without throwing when omitted", () => {
    const warn = jest.fn();
    const toast = jest.fn();
    notifyOfflineSendBlocked({ warn, showToast: toast });
    expect(warn).toHaveBeenCalledTimes(1);
    expect(toast).toHaveBeenCalledTimes(1);

    expect(() => notifyOfflineSendBlocked({ warn })).not.toThrow();
    expect(warn).toHaveBeenCalledTimes(2);
  });
});
