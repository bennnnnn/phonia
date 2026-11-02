/**
 * The phone reads geo intent exactly the way the server does, so it reads GPS
 * for the same messages the server answers from the user's location.
 * docs/fixtures/geo_intent_cases.json is shared with the API test
 * (app/tests/modules/web_search/test_geo_intent_contract.py), so a rule changed
 * on one side alone fails a suite.
 */
import {
  isAmbiguousLocalPlacesQuery,
  isDistanceQuery,
  isGeoQuery,
  isLocationQuestion,
  isProximityQuery,
} from "@/lib/places/localPlacesQuery";

import fixture from "@/../../docs/fixtures/geo_intent_cases.json";

type Reader = "proximity" | "distance" | "location_question" | "ambiguous_places";
type GeoCase = { text: string; reads: string[] };
type Contract = { readers: Record<string, string>; cases: Record<string, GeoCase[]> };

const READERS: Record<Reader, (text: string) => boolean> = {
  proximity: isProximityQuery,
  distance: isDistanceQuery,
  location_question: isLocationQuestion,
  ambiguous_places: isAmbiguousLocalPlacesQuery,
};
const READER_NAMES = Object.keys(READERS) as Reader[];

const contract: Contract = fixture;
const cases = Object.entries(contract.cases).flatMap(([group, rows]) =>
  rows.map((c) => [`${group} ${JSON.stringify(c.text).slice(0, 70)}`, c] as const),
);

describe("geo intent contract", () => {
  it("names only readers both sides have", () => {
    expect(Object.keys(contract.readers).sort()).toEqual([...READER_NAMES].sort());
    for (const [, c] of cases) {
      for (const name of c.reads) expect(READER_NAMES).toContain(name);
    }
  });

  it.each(cases)("%s", (_label, c) => {
    const reads = READER_NAMES.filter((name) => READERS[name](c.text));
    expect(reads).toEqual(c.reads);
  });
});

describe("isGeoQuery", () => {
  // The phone's composite: a nearby, distance or where-am-I ask needs a fix.
  // The server's is_geo_query adds a local-weather ask instead, so this half
  // is the phone's own and is not in the shared fixture.
  const needsFix = new Set<string>(["proximity", "distance", "location_question"]);

  it.each(cases)("%s", (_label, c) => {
    expect(isGeoQuery(c.text)).toBe(c.reads.some((name) => needsFix.has(name)));
  });
});
