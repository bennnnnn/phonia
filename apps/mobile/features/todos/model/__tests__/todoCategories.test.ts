import {
  categoryText,
  isNoCategory,
  resolveCategoryName,
} from "@/features/todos/model/todoCategories";

const t = (key: string) => key;

describe("todo categories", () => {
  it("treats a blank topic and General as no category", () => {
    expect(isNoCategory("")).toBe(true);
    expect(isNoCategory("General")).toBe(true);
    expect(categoryText("General", t)).toBeNull();
  });

  it("translates built-in ids and keeps a custom name", () => {
    expect(categoryText("work", t)).toBe("todos.category_work");
    expect(categoryText("School", t)).toBe("School");
  });

  it("collapses a typed built-in name onto its id", () => {
    expect(resolveCategoryName("  Work ")).toBe("work");
    expect(resolveCategoryName("no category")).toBe("General");
    expect(resolveCategoryName("School")).toBe("School");
    expect(resolveCategoryName("   ")).toBeNull();
  });
});
