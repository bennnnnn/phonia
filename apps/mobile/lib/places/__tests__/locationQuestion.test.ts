/**
 * The phone reads "where am I?" exactly the way the server does.
 * docs/fixtures/geo_intent_cases.json is shared with the API test
 * (app/tests/modules/web_search/test_geo_intent_contract.py), so a rule changed
 * on one side alone fails a suite. The phone keeps only the location question:
 * the app does not use the device's location.
 */
import { isLocationQuestion } from "@/lib/places/locationQuestion";

import fixture from "@/../../docs/fixtures/geo_intent_cases.json";

type GeoCase = { text: string; reads: string[] };
type Contract = { readers: Record<string, string>; cases: Record<string, GeoCase[]> };

const contract: Contract = fixture;
const cases = Object.entries(contract.cases).flatMap(([group, rows]) =>
  rows.map((c) => [`${group} ${JSON.stringify(c.text).slice(0, 70)}`, c] as const),
);

describe("location question contract", () => {
  it("names the reader the phone has", () => {
    expect(Object.keys(contract.readers)).toContain("location_question");
  });

  it.each(cases)("%s", (_label, c) => {
    expect(isLocationQuestion(c.text)).toBe(c.reads.includes("location_question"));
  });
});
