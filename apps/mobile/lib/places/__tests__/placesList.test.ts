import {
  googleMapsSearchUrl,
  isGenericSearchUrl,
  parsePlacesJson,
  repairBrokenMarkdownLinks,
  resolvePlaceLinkUrl,
  resolvePlaces,
  stripPlacesContent,
} from "@/lib/places/placesList";

describe("placesList", () => {
  it("parses places fence", () => {
    const content = `Here are salons:

\`\`\`places
[{"name":"CODE Salon","url":"https://example.com/code","note":"4.7 stars","price":"$$"}]
\`\`\``;
    expect(resolvePlaces(content)).toEqual([
      {
        name: "CODE Salon",
        url: "https://example.com/code",
        note: "4.7 stars",
        price: "$$",
      },
    ]);
  });

  it("repairs broken markdown links with dollar delimiters", () => {
    const broken =
      "1. [CODE Salon]$https://www.yelp.com/biz/code-salon$ — Top-rated";
    expect(repairBrokenMarkdownLinks(broken)).toBe(
      "1. [CODE Salon](https://www.yelp.com/biz/code-salon) — Top-rated",
    );
  });

  it("does not merge adjacent inline math spans into a broken link", () => {
    // Reported live ("leaked latex"): `Integrate 9 over $x \in [0,2]$ \times
    // $y \in [1,3]$:` — the old regex matched `[0,2]$ \times $` and rewrote it
    // to `[0,2]( \times )`, leaking the `$` delimiters and painting `0,2` blue.
    const math = "Integrate 9 over $x \\in [0,2]$ \\times $y \\in [1,3]$:";
    expect(repairBrokenMarkdownLinks(math)).toBe(math);
    expect(repairBrokenMarkdownLinks(math)).not.toContain("](");
  });

  it("still repairs a www. url without an explicit scheme", () => {
    const broken = "[Google]$www.google.com$";
    expect(repairBrokenMarkdownLinks(broken)).toBe("[Google](www.google.com)");
  });

  it("parses minimal rows", () => {
    expect(parsePlacesJson('[{"name":"A","address":"1 Main St"}]')).toEqual([
      {
        name: "A",
        url: "https://www.google.com/maps/search/?api=1&query=A%2C%201%20Main%20St",
        address: "1 Main St",
      },
    ]);
  });

  it("resolves to google maps using address", () => {
    const url = resolvePlaceLinkUrl({
      name: "CODE Salon",
      url: "https://www.yelp.com/search?find_desc=Hair+Salons",
      address: "123 Market St, San Francisco",
    });
    expect(url).toContain("google.com/maps/search");
    expect(url).toContain("123%20Market%20St");
    expect(isGenericSearchUrl("https://www.yelp.com/search?q=x")).toBe(true);
    expect(isGenericSearchUrl("https://www.google.com/search?q=x")).toBe(true);
    expect(isGenericSearchUrl("https://evilgoogle.com/search?q=x")).toBe(false);
  });

  it("preserves direct venue URLs", () => {
    expect(
      resolvePlaceLinkUrl({
        name: "Benu",
        url: "https://www.yelp.com/biz/benu-san-francisco",
        address: "22 Hawthorne St",
      }),
    ).toBe("https://www.yelp.com/biz/benu-san-francisco");
  });

  it("builds maps url from name when address missing", () => {
    expect(googleMapsSearchUrl("CODE Salon")).toContain("CODE%20Salon");
  });

  it("resolvePlaces ignores plain numbered lists (math, steps, etc.)", () => {
    const math = `Area: 12 cm²

1. **Base (b):**
   6 cm (the bottom side)
2. **Height (h):**
   4 cm (the vertical side)
3. **Hypotenuse (c):**
   ≈ 7.21 cm`;

    expect(resolvePlaces(math)).toEqual([]);
  });

  it("resolvePlaces reads mis-tagged json venue arrays", () => {
    const content = `Here are gas stations:

\`\`\`json
[{"name":"Shell","url":"https://maps.google.com/?q=shell","address":"123 Market St","price":"$"}]
\`\`\``;
    expect(resolvePlaces(content)).toEqual([
      expect.objectContaining({ name: "Shell", address: "123 Market St" }),
    ]);
    const places = resolvePlaces(content);
    expect(stripPlacesContent(content, places)).not.toContain("```json");
  });

  it("resolvePlaces only reads explicit places fences", () => {
    const content = `Intro
1. **Old List Item** – should ignore
\`\`\`places
[{"name":"From Fence","url":"https://example.com","address":"1 Main"}]
\`\`\``;
    expect(resolvePlaces(content)).toEqual([
      expect.objectContaining({ name: "From Fence" }),
    ]);
  });

  it("stripPlacesContent removes only the places fence", () => {
    const content = `Here are picks:

1. **Benu** – fusion ($$)

\`\`\`places
[{"name":"Benu","url":"https://x.com","address":"SF"}]
\`\`\``;
    const places = resolvePlaces(content);
    const stripped = stripPlacesContent(content, places);
    expect(stripped).toContain("Here are picks");
    expect(stripped).toContain("**Benu**");
    expect(stripped).not.toContain("```places");
  });
});
