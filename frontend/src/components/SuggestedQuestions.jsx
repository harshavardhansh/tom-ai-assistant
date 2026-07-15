export default function SuggestedQuestions({ questions, onAsk }) {
  if (!questions || questions.length === 0) return null;
  return (
    <div className="suggested">
      <h4>Suggested follow-ups</h4>
      <div className="example-row">
        {questions.map((q, i) => (
          <button key={i} className="chip" onClick={() => onAsk(q)}>
            {q}
          </button>
        ))}
      </div>
    </div>
  );
}
