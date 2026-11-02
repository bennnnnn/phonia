import { clearQuizAttempts, quizAttempt, saveQuizAttempt } from "@/lib/lesson/quizAttempts";

beforeEach(() => clearQuizAttempts());

it("keeps the 200 most recently answered quizzes (LEAK-07)", () => {
  for (let index = 0; index < 201; index += 1) saveQuizAttempt(`quiz-${index}`, { picked: 1, checked: true });
  expect(quizAttempt("quiz-0")).toBeUndefined();
  expect(quizAttempt("quiz-1")).toEqual({ picked: 1, checked: true });
  expect(quizAttempt("quiz-200")).toEqual({ picked: 1, checked: true });
});

it("counts a quiz answered again as the most recent", () => {
  for (let index = 0; index < 200; index += 1) saveQuizAttempt(`quiz-${index}`, { picked: 0, checked: false });
  saveQuizAttempt("quiz-0", { picked: 2, checked: true });
  saveQuizAttempt("quiz-new", { picked: 1, checked: false });
  expect(quizAttempt("quiz-0")).toEqual({ picked: 2, checked: true });
  expect(quizAttempt("quiz-1")).toBeUndefined();
});
