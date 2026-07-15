// Thin API client. A token provider (from MSAL) is injected when auth is on;
// in dev it returns null and no Authorization header is sent.

async function authHeaders(getToken) {
  const headers = { "Content-Type": "application/json" };
  if (getToken) {
    const token = await getToken();
    if (token) headers.Authorization = `Bearer ${token}`;
  }
  return headers;
}

export async function sendChat(question, sessionId, getToken, persona = "professional") {
  const res = await fetch("/api/v1/chat", {
    method: "POST",
    headers: await authHeaders(getToken),
    body: JSON.stringify({ question, session_id: sessionId, persona }),
  });
  if (!res.ok) {
    const detail = await res.text().catch(() => "");
    throw new Error(`Chat failed (${res.status}). ${detail}`);
  }
  return res.json();
}

export async function exportAsset(answerMarkdown, title, fmt, processFlow, getToken) {
  const res = await fetch("/api/v1/export", {
    method: "POST",
    headers: await authHeaders(getToken),
    body: JSON.stringify({
      answer_markdown: answerMarkdown,
      title,
      fmt,
      process_flow: processFlow || null,
    }),
  });
  if (!res.ok) throw new Error(`Export failed (${res.status}).`);
  const blob = await res.blob();
  const disposition = res.headers.get("Content-Disposition") || "";
  const match = disposition.match(/filename="(.+?)"/);
  const filename = match ? match[1] : `tom-response.${fmt}`;
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}
