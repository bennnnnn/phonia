import { Linking } from "react-native";

import { openPlaceLink } from "@/lib/places/openPlaceLink";

jest.mock("react-native", () => ({
  Linking: {
    openURL: jest.fn(),
  },
}));

describe("openPlaceLink", () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it("opens direct venue URLs", async () => {
    await openPlaceLink("https://www.yelp.com/biz/example", "Example");
    expect(Linking.openURL).toHaveBeenCalledWith("https://www.yelp.com/biz/example");
  });

  it("falls back to maps search for generic URLs", async () => {
    await openPlaceLink("https://www.yelp.com/search?q=cafe", "Blue Bottle");
    expect(Linking.openURL).toHaveBeenCalledWith(
      expect.stringContaining("google.com/maps/search"),
    );
    expect(Linking.openURL).toHaveBeenCalledWith(expect.stringContaining("Blue%20Bottle"));
  });

  it("uses label fallback when url is empty", async () => {
    await openPlaceLink("", "Nopa");
    expect(Linking.openURL).toHaveBeenCalledWith(
      expect.stringContaining("google.com/maps/search"),
    );
  });

  it("does not open javascript: venue URLs", async () => {
    await openPlaceLink("javascript:alert(1)", "Evil");
    expect(Linking.openURL).not.toHaveBeenCalledWith("javascript:alert(1)");
    expect(Linking.openURL).toHaveBeenCalledWith(
      expect.stringContaining("google.com/maps/search"),
    );
  });
});
