import { fitImageToStage } from "@/lib/fitImageToStage";

describe("fitImageToStage", () => {
  it("keeps a small photo at its own size instead of stretching it to the stage", () => {
    expect(fitImageToStage(200, 100, 400, 800)).toEqual({ width: 200, height: 100 });
  });

  it("scales a landscape photo down to the stage width", () => {
    expect(fitImageToStage(4000, 2000, 400, 800)).toEqual({ width: 400, height: 200 });
  });

  it("scales a portrait photo down to the stage height", () => {
    expect(fitImageToStage(1000, 4000, 400, 800)).toEqual({ width: 200, height: 800 });
  });
});
