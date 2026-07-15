import { useRef, useState } from "react";

export default function Composer({ onSend, disabled }) {
  const [value, setValue] = useState("");
  const ref = useRef(null);

  function submit() {
    const q = value.trim();
    if (!q || disabled) return;
    onSend(q);
    setValue("");
    if (ref.current) ref.current.style.height = "auto";
  }

  function onKeyDown(e) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      submit();
    }
  }

  function onInput(e) {
    setValue(e.target.value);
    e.target.style.height = "auto";
    e.target.style.height = Math.min(e.target.scrollHeight, 160) + "px";
  }

  return (
    <div className="composer">
      <div className="composer-inner">
        <div className="field">
          <textarea
            ref={ref}
            rows={1}
            value={value}
            placeholder="Ask about a process, level, role, control, or concept…"
            onChange={onInput}
            onKeyDown={onKeyDown}
            aria-label="Ask a question"
          />
          <button className="send" onClick={submit} disabled={disabled || !value.trim()}>
            Ask
          </button>
        </div>
        <div className="hint">
          Answers are grounded in the TOM knowledge base. Press Enter to send, Shift+Enter for a new line.
        </div>
      </div>
    </div>
  );
}
