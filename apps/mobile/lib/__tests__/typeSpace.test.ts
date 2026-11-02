import { IconSize } from "@/ui/icons/sizes";
import { Layer } from "@/lib/layer";
import { Radius } from "@/lib/radius";
import { Space } from "@/lib/space";
import { Type, Weight } from "@/lib/type";

describe("type and space tokens", () => {
  it("owns the screen type roles", () => {
    expect(Type.body.fontSize).toBe(16);
    expect(Type.secondary.fontSize).toBe(14);
    expect(Type.caption.fontSize).toBe(12);
    expect(Type.compact.fontSize).toBe(13);
    expect(Type.label.fontSize).toBe(14);
    expect(Type.callout.fontSize).toBe(15);
    expect(Type.navTitle.fontSize).toBe(17);
    expect(Type.title.fontSize).toBe(20);
    expect(Type.display.fontSize).toBe(28);
    expect(Type.body.fontFamily).toBe("SourceSans3");
    expect(Type.label.fontFamily).toBe("SourceSans3-Semibold");
    expect(Type.display.fontFamily).toBe("SourceSans3-Bold");
  });

  it("pairs every weight with its own Source Sans file", () => {
    expect(Weight.regular).toEqual({ fontFamily: "SourceSans3", fontWeight: "400" });
    expect(Weight.medium).toEqual({ fontFamily: "SourceSans3-Medium", fontWeight: "400" });
    expect(Weight.semibold).toEqual({ fontFamily: "SourceSans3-Semibold", fontWeight: "400" });
    expect(Weight.bold).toEqual({ fontFamily: "SourceSans3-Bold", fontWeight: "400" });
  });

  it("lets multiline roles use scaled platform line boxes", () => {
    for (const role of [
      Type.body,
      Type.secondary,
      Type.compact,
      Type.callout,
      Type.title,
      Type.navTitle,
      Type.display,
      Type.h1,
      Type.h2,
      Type.h3,
      Type.h4,
      Type.h5,
      Type.h6,
    ]) {
      expect(role).not.toHaveProperty("lineHeight");
    }
  });

  it("uses a 4pt spacing scale", () => {
    expect(Space.xxs).toBe(4);
    expect(Space.xs).toBe(8);
    expect(Space.sm).toBe(12);
    expect(Space.md).toBe(16);
    expect(Space.gutter).toBe(20);
    expect(Space.lg).toBe(24);
    expect(Space.xl).toBe(32);
    expect(Space.minTouch).toBe(44);
  });

  it("owns chrome radius, icon, and overlay layers", () => {
    expect(Radius.md).toBe(12);
    expect(Radius.card).toBe(20);
    expect(Radius.menu).toBe(24);
    expect(Radius.sheet).toBe(28);
    expect(Radius.dialog).toBe(28);
    expect(Radius.composer).toBe(28);
    expect(IconSize.xxs).toBe(14);
    expect(IconSize.xs).toBe(16);
    expect(IconSize.sm).toBe(20);
    expect(IconSize.md).toBe(24);
    expect(IconSize.lg).toBe(28);
    expect(IconSize.xl).toBe(40);
    expect(IconSize.hero).toBe(56);
    expect(Layer.toast).toBe(9999);
    expect(Layer.drawer).toBeGreaterThan(Layer.composer);
    expect(Layer.sheet).toBeGreaterThan(Layer.composerExpanded);
    expect(Layer.composerExpanded).toBeGreaterThan(Layer.composer);
    expect(Layer.composer).toBeGreaterThan(Layer.header);
  });
});
