import { accountDeleteFailureKey, isAccountDeleteComplete } from "@/lib/accountDelete";

describe("isAccountDeleteComplete", () => {
  it("treats 401/404 as the account already gone", () => {
    expect(isAccountDeleteComplete({ status: 401 })).toBe(true);
    expect(isAccountDeleteComplete({ status: 404 })).toBe(true);
  });

  it("does not treat a failed wipe as done", () => {
    expect(isAccountDeleteComplete({ status: 500 })).toBe(false);
    expect(isAccountDeleteComplete(new Error("network"))).toBe(false);
  });
});

describe("accountDeleteFailureKey", () => {
  it("says Recall is unavailable, to try again, when the API could not serve the delete", () => {
    expect(accountDeleteFailureKey("unavailable")).toBe("common.service_unavailable");
  });

  it("says the delete failed otherwise", () => {
    expect(accountDeleteFailureKey("failed")).toBe("settings.delete_failed");
  });
});
