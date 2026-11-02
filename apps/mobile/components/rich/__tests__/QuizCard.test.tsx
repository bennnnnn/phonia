import { fireEvent, render } from "@testing-library/react-native";
import { AccessibilityInfo } from "react-native";

import { QuizCard } from "@/components/rich/QuizCard";

jest.mock("@/lib/i18n", () => ({
  __esModule: true,
  default: { t: (key: string) => key },
}));
jest.mock("@/components/CodeBlock", () => {
  const { Text } = jest.requireActual("react-native");
  return {
    CodeBlock: ({ code, lang }: { code: string; lang: string }) => (
      <Text>{`${lang}:${code}`}</Text>
    ),
  };
});
jest.mock("@/lib/haptics", () => ({
  selection: jest.fn(),
  notifySuccess: jest.fn(),
  notifyWarning: jest.fn(),
}));

const quiz = (explanation = "Only 6 and 8 are greater than 4.") =>
  JSON.stringify({
    question: "What will this print?",
    options: ["[2, 4, 6, 8]", "[12, 16]", "[6, 8]"],
    answer: 1,
    explanation,
  });

describe("QuizCard", () => {
  it("checks a right answer and explains it", async () => {
    const view = await render(<QuizCard content={quiz()} />);
    expect(view.getByText("What will this print?")).toBeTruthy();
    expect(view.queryByText("rich.quiz_correct")).toBeNull();
    await fireEvent.press(view.getByText("[12, 16]"));
    await fireEvent.press(view.getByText("rich.quiz_check"));
    // The verdict is its own line above the explanation, as in ChatGPT.
    expect(view.getByText("rich.quiz_correct")).toBeTruthy();
    expect(view.getByText("Only 6 and 8 are greater than 4.")).toBeTruthy();
  });

  it("says the verdict to VoiceOver when checked here, not when a checked card mounts again", async () => {
    const announce = jest.spyOn(AccessibilityInfo, "announceForAccessibility").mockImplementation(() => undefined);
    announce.mockClear();
    const content = quiz("Announced once.");
    const view = await render(<QuizCard content={content} />);
    await fireEvent.press(view.getByText("[2, 4, 6, 8]"));
    await fireEvent.press(view.getByText("rich.quiz_check"));
    expect(announce.mock.calls).toEqual([["rich.quiz_wrong"]]);
    await view.unmount();
    // The attempt is kept, so the card comes back checked: nothing new to say.
    const again = await render(<QuizCard content={content} />);
    expect(again.getByText("rich.quiz_wrong")).toBeTruthy();
    expect(announce).toHaveBeenCalledTimes(1);
    announce.mockRestore();
  });

  it("shows the exercise pill and the code inside the card", async () => {
    const content = JSON.stringify({
      label: "Exercise 1",
      question: "What will this Python code print?",
      code: "numbers = [2, 4, 6, 8]\nprint(numbers[-1])",
      options: ["2", "8"],
      answer: 1,
      explanation: "`-1` is the last item.",
    });
    const view = await render(<QuizCard content={content} />);
    expect(view.getByText("Exercise 1")).toBeTruthy();
    expect(
      view.getByText("python:numbers = [2, 4, 6, 8]\nprint(numbers[-1])"),
    ).toBeTruthy();
  });

  it("draws code in the explanation as a code block", async () => {
    const content = JSON.stringify({
      question: "What does enumerate give?",
      options: ["Only the values", "Index and value"],
      answer: 1,
      explanation:
        "`enumerate()` gives both.\n\n```python\nfor i, n in enumerate([3, 3]):\n    print(i, n)\n```",
    });
    const view = await render(<QuizCard content={content} />);
    await fireEvent.press(view.getByText("Only the values"));
    await fireEvent.press(view.getByText("rich.quiz_check"));
    expect(view.getByText("rich.quiz_wrong")).toBeTruthy();
    expect(
      view.getByText("python:for i, n in enumerate([3, 3]):\n    print(i, n)"),
    ).toBeTruthy();
  });

  it("says a wrong answer is not quite, and a new pick tries again", async () => {
    const view = await render(
      <QuizCard content={quiz("Wrong-path explanation.")} />,
    );
    await fireEvent.press(view.getByText("[6, 8]"));
    await fireEvent.press(view.getByText("rich.quiz_check"));
    expect(view.getByText("rich.quiz_wrong")).toBeTruthy();
    await fireEvent.press(view.getByText("[12, 16]"));
    expect(view.queryByText("rich.quiz_wrong")).toBeNull();
    expect(view.getByText("rich.quiz_check")).toBeTruthy();
  });

  it("keeps the answer when the card is drawn again", async () => {
    const content = quiz("Remembered explanation.");
    const first = await render(<QuizCard content={content} />);
    await fireEvent.press(first.getByText("[12, 16]"));
    await fireEvent.press(first.getByText("rich.quiz_check"));
    await first.unmount();
    const again = await render(<QuizCard content={content} />);
    expect(again.getByText("rich.quiz_correct")).toBeTruthy();
  });

  it("draws nothing while the question is still streaming in", async () => {
    const view = await render(<QuizCard content='{"question": "What will' />);
    expect(view.toJSON()).toBeNull();
  });

  it("shows a question it cannot check as text", async () => {
    const view = await render(
      <QuizCard content='{"question": "Pick", "options": ["a"]}' />,
    );
    expect(view.getByTestId("quiz-card-text")).toBeTruthy();
    expect(view.getByText("Pick")).toBeTruthy();
    expect(view.getByText("A) a")).toBeTruthy();
    expect(view.queryByText("rich.quiz_show_answer")).toBeNull();
  });

  it("reads a finished fence with broken JSON and keeps the answer behind a tap", async () => {
    const broken = [
      "{",
      '  "label": "Exercise 2",',
      '  "question": "What is `len(\\"hi\\")`?",',
      '  "code": "print(len(\\"hi\\"))",',
      '  "options": ["1", "2", "3",],',
      '  "answer": 1,',
      '  "explanation": "Two letters,',
      'so 2."',
      "}",
    ].join("\n");
    const view = await render(<QuizCard content={broken} />);
    expect(view.getByText("Exercise 2")).toBeTruthy();
    expect(view.getByText('python:print(len("hi"))')).toBeTruthy();
    expect(view.getByText("B) 2")).toBeTruthy();
    expect(view.queryByText(/Two letters/)).toBeNull();
    await fireEvent.press(view.getByText("rich.quiz_show_answer"));
    expect(view.getByText(/Two letters/)).toBeTruthy();
  });

  it("draws a flashcard: the front, with the back behind Show answer", async () => {
    const card = JSON.stringify({
      label: "Card 1",
      question: "hablar",
      explanation: "to speak. Hablo español.",
    });
    const view = await render(<QuizCard content={card} />);
    expect(view.getByText("Card 1")).toBeTruthy();
    expect(view.getByText("hablar")).toBeTruthy();
    expect(view.queryByText("to speak. Hablo español.")).toBeNull();
    await fireEvent.press(view.getByText("rich.quiz_show_answer"));
    expect(view.getByText("to speak. Hablo español.")).toBeTruthy();
  });

  it("checks a true/false question", async () => {
    const tf = JSON.stringify({
      question: "The Battle of Hastings was in 1066.",
      options: ["True", "False"],
      answer: 0,
      explanation: "William of Normandy won it in October 1066.",
    });
    const view = await render(<QuizCard content={tf} />);
    await fireEvent.press(view.getByText("False"));
    await fireEvent.press(view.getByText("rich.quiz_check"));
    expect(view.getByText("rich.quiz_wrong")).toBeTruthy();
  });

  it("draws nothing for JSON after a line of prose, never its answer key", async () => {
    const keyed =
      'Here you go:\n{"question":"Q","options":["a","b"],"answer":1,"explanation":"secret"}';
    const view = await render(<QuizCard content={keyed} />);
    expect(view.toJSON()).toBeNull();
  });

  it("shows a question written as plain text", async () => {
    const view = await render(<QuizCard content="Which loop prints 1 to 5?" />);
    expect(view.getByText("Which loop prints 1 to 5?")).toBeTruthy();
  });

  it("draws nothing for a finished fence with no question in it", async () => {
    const view = await render(<QuizCard content='{"note": "x",}' />);
    expect(view.toJSON()).toBeNull();
  });
});
