/**
 * The prefilter never keeps the server from a send it would draw or look up.
 * Every positive case the server pins in docs/fixtures/image_intent_cases.json,
 * and every photo or picture turn in the API's behavior sweep, must be asked.
 */
import { mightBeImageTurn } from "@/features/images/model/imageIntentPrefilter";

import fixture from "../../../../../../docs/fixtures/image_intent_cases.json";
import followups from "../../../../../api/app/tests/behavior/sweep_corpus/followups.json";
import intentLookalikes from "../../../../../api/app/tests/behavior/sweep_corpus/intent_lookalikes.json";
import pictureLanguages from "../../../../../api/app/tests/behavior/sweep_corpus/picture_languages.json";
import searchPhotos from "../../../../../api/app/tests/behavior/sweep_corpus/search_photos.json";
import stemWordProblems from "../../../../../api/app/tests/behavior/sweep_corpus/stem_word_problems.json";
import writingLanguages from "../../../../../api/app/tests/behavior/sweep_corpus/writing_languages.json";

type Turn = { role: string; content: string; model?: string };
type Row = { id: string; role: string; content: string };
type SweepEntry = { id: string; prompt: string; expect: string; history?: string[][] };

const IMAGE = "[Image: /attachments/aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee/file]";
const AFTER_PICTURE: Turn[] = [
  { role: "user", content: `Generate image: ${fixture.revise_previous_subject}` },
  { role: "assistant", content: IMAGE },
];

const rows = (turns: readonly Turn[]): Row[] =>
  turns.map((turn, i) => ({ id: `m${i}`, role: turn.role, content: turn.content }));
const label = (text: string) => JSON.stringify(text).slice(0, 60);

type Positive = { text: string; thread: Turn[]; attached: boolean };

function fixturePositives(): Positive[] {
  const out: Positive[] = [];
  for (const phrase of fixture.phrases) {
    if (phrase.generate !== null || phrase.lookup !== null) {
      out.push({ text: phrase.text, thread: [], attached: false });
    }
    if (phrase.revise !== null) out.push({ text: phrase.text, thread: AFTER_PICTURE, attached: false });
  }
  for (const thread of fixture.threads) {
    if (thread.generate === null) continue;
    out.push({
      text: thread.text,
      thread: thread.priors.map((content) => ({ role: "user", content })),
      attached: false,
    });
  }
  const threads = fixture.composer_threads as Record<string, Turn[]>;
  for (const composer of fixture.composer as { text: string; thread: string; attached?: boolean; generate?: string; lookup?: string }[]) {
    if (composer.generate === undefined && composer.lookup === undefined) continue;
    out.push({ text: composer.text, thread: threads[composer.thread], attached: composer.attached ?? false });
  }
  return out;
}

function sweepPositives(): Positive[] {
  const corpora = [
    followups, intentLookalikes, pictureLanguages, searchPhotos, stemWordProblems, writingLanguages,
  ] as SweepEntry[][];
  return corpora.flat()
    .filter((entry) => entry.expect === "photo" || entry.expect === "image_gen")
    .map((entry) => ({
      text: entry.prompt,
      thread: (entry.history ?? []).map(([role, content]) => ({ role, content })),
      attached: false,
    }));
}

describe("image intent prefilter", () => {
  const fixtureCases = fixturePositives();
  const sweepCases = sweepPositives();

  it("has the server's cases to run", () => {
    expect(fixtureCases.length).toBeGreaterThan(400);
    expect(sweepCases.length).toBeGreaterThanOrEqual(70);
  });

  it.each(fixtureCases.map((c) => [label(c.text), c] as const))(
    "asks the server about fixture case %s",
    (_label, c) => {
      expect(mightBeImageTurn(c.text, rows(c.thread), c.attached)).toBe(true);
    },
  );

  it.each(sweepCases.map((c) => [label(c.text), c] as const))(
    "asks the server about sweep turn %s",
    (_label, c) => {
      expect(mightBeImageTurn(c.text, rows(c.thread), c.attached)).toBe(true);
    },
  );

  it.each([
    "hello",
    "what is 2+2",
    "thanks",
    "explain quantum entanglement",
    "write a poem about the sea",
    "remind me to call mom at 5",
    "turn off the lights",
  ])("sends %j straight to chat on an empty thread", (text) => {
    expect(mightBeImageTurn(text, [], false)).toBe(false);
  });

  it.each([
    "Zeichne mir eine Katze mit Hut und erkläre auch, was ein schwarzes Loch ist",
    "Dibújame un dragón",
    "¿Me dibujas un dragón?",
    "Píntame un atardecer",
    "Mi disegni un panda?",
    "Tu me dessines un panda ?",
    "Нарисуешь мне кота?",
    "Bana bir panda çizer misin?",
    "ድመት ሳልልኝ",
    "የአንበሳ ምስል ፍጠር",
    "Mal mir eine Katze mit Hut",
    "Explica qué es un agujero negro y dibújame un gato",
    "Peux-tu me peindre un chat ?",
    "Malen Sie mir eine Katze",
    "Male uns einen Drachen",
    "Crea una ilustracion de un leon",
    "Crie uma ilustração de um leão",
    "Erstelle ein Bild von einem Löwen",
  ])("asks the server about a picture asked in another language: %j", (text) => {
    expect(mightBeImageTurn(text, [], false)).toBe(true);
  });

  it.each([
    "Hola, ¿qué tal?",
    "Wie spät ist es in Berlin?",
    "Привет, как дела?",
    "Bugün hava nasıl?",
    // Everyday words that once started a picture word: "mal" (bad, once), "peine", "Bildung".
    "Me siento mal hoy",
    "Estou mal",
    "Erklär mal die Steuer",
    "Ce n'est pas la peine",
    "Bildung in Deutschland",
    "Is my cat male or female?",
    "Ho tre valigie, male?",
  ])("sends %j in another language straight to chat", (text) => {
    expect(mightBeImageTurn(text, [], false)).toBe(false);
  });

  it("asks about an edit word only with an image attached", () => {
    expect(mightBeImageTurn("crop it", [], false)).toBe(false);
    expect(mightBeImageTurn("crop it", [], true)).toBe(true);
    expect(mightBeImageTurn("Could you remove the background", [], true)).toBe(true);
  });

  it("asks about any follow-up to a picture, and none to a text reply", () => {
    // No picture word anywhere: only the picture itself makes "White" an edit.
    const question = "which bird is this one, and where does it usually live in winter?";
    const afterPicture = rows([{ role: "user", content: question }, { role: "assistant", content: IMAGE }]);
    const afterText = rows([{ role: "user", content: question }, { role: "assistant", content: "A robin." }]);
    expect(mightBeImageTurn("White", afterPicture, false)).toBe(true);
    expect(mightBeImageTurn("White", afterText, false)).toBe(false);
  });

  it("reads the picture the server stored, not the phone's pending or failed rows", () => {
    const thread: Row[] = [
      ...rows(AFTER_PICTURE),
      { id: "local-1", role: "user", content: "make it red and add a long caption about the weekend trip" },
      { id: "image-gen-failed", role: "assistant", content: "" },
    ];
    expect(mightBeImageTurn("White", thread, false)).toBe(true);
  });

  it("asks about a short confirmation after a picture request, not after plain chat", () => {
    const asked = rows([{ role: "user", content: "draw me a dog" }, { role: "assistant", content: "Which style?" }]);
    const chatted = rows([{ role: "user", content: "tell me about dogs" }, { role: "assistant", content: "Dogs…" }]);
    expect(mightBeImageTurn("do it", asked, false)).toBe(true);
    expect(mightBeImageTurn("do it!!!", [...asked, ...rows([{ role: "user", content: "do it" }])], false)).toBe(true);
    expect(mightBeImageTurn("do it", chatted, false)).toBe(false);
    expect(mightBeImageTurn("please go ahead and do it now, I have been waiting all day", asked, false)).toBe(false);
  });
});
