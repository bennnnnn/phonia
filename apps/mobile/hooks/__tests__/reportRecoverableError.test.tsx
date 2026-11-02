import { Alert } from "react-native";

import type { ActionFeedbackApi } from "@/contexts/actionFeedbackCore";
import {
  reportRecoverableError,
  reportRecoverableWarning,
} from "@/lib/reportRecoverableError";

function fakeFeedback(
  overrides: Partial<ActionFeedbackApi> = {},
): ActionFeedbackApi {
  return {
    show: jest.fn(),
    success: jest.fn(),
    info: jest.fn(),
    warning: jest.fn(),
    error: jest.fn(),
    dismiss: jest.fn(),
    ...overrides,
  };
}

describe("reportRecoverableError", () => {
  beforeEach(() => {
    jest.spyOn(Alert, "alert").mockImplementation(() => {});
  });

  afterEach(() => {
    jest.restoreAllMocks();
  });

  it("uses ActionFeedback when present", () => {
    const feedback = fakeFeedback();
    reportRecoverableError(feedback, "Could not save");
    expect(feedback.error).toHaveBeenCalledWith("Could not save");
    expect(Alert.alert).not.toHaveBeenCalled();
  });

  it("falls back to Alert when the provider is absent", () => {
    reportRecoverableError(null, "Could not save");
    expect(Alert.alert).toHaveBeenCalledWith("Could not save");
  });

  it("routes warnings through the banner", () => {
    const feedback = fakeFeedback();
    reportRecoverableWarning(feedback, "HEIC");
    expect(feedback.warning).toHaveBeenCalledWith("HEIC");
    expect(Alert.alert).not.toHaveBeenCalled();
  });
});
