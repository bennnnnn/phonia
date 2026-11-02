/**
 * The Reduce Motion setting is read asynchronously. A figure that autoplays
 * must be able to tell "not known yet" from "off", and once any screen has
 * read the setting, later mounts start from the real value.
 */
import { renderHook, waitFor } from "@testing-library/react-native";
import { AccessibilityInfo } from "react-native";

import { useReduceMotion, useReduceMotionSetting } from "@/lib/reduceMotion";

describe("useReduceMotionSetting", () => {
  it("is unknown on the first mount, then remembered for every later one", async () => {
    jest.spyOn(AccessibilityInfo, "isReduceMotionEnabled").mockResolvedValue(true);

    const first: (boolean | null)[] = [];
    await renderHook(() => {
      const value = useReduceMotionSetting();
      first.push(value);
      return value;
    });
    expect(first[0]).toBeNull();
    await waitFor(() => expect(first.at(-1)).toBe(true));

    const later: (boolean | null)[] = [];
    await renderHook(() => {
      const value = useReduceMotionSetting();
      later.push(value);
      return value;
    });
    expect(later[0]).toBe(true);

    // The boolean hook keeps its old contract for everything else.
    const plain = await renderHook(() => useReduceMotion());
    expect(plain.result.current).toBe(true);
  });
});
