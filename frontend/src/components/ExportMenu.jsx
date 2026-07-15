import { useState } from "react";
import { exportAsset } from "../api/client.js";

const FORMATS = [
  { fmt: "docx", label: "Word (.docx)" },
  { fmt: "pptx", label: "PowerPoint (.pptx)" },
  { fmt: "pdf", label: "PDF (.pdf)" },
];

export default function ExportMenu({ markdown, title, processFlow, getToken }) {
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);

  async function handleExport(fmt) {
    setBusy(true);
    setOpen(false);
    try {
      await exportAsset(markdown, title, fmt, processFlow, getToken);
    } catch (e) {
      console.error(e);
      alert("Export failed. Please try again.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="export-wrap">
      <button
        className="tool-btn"
        disabled={busy}
        onClick={() => setOpen((v) => !v)}
        aria-haspopup="menu"
        aria-expanded={open}
      >
        {busy ? "Preparing…" : "Export ▾"}
      </button>
      {open && (
        <div className="export-menu" role="menu">
          {FORMATS.map((f) => (
            <button key={f.fmt} role="menuitem" onClick={() => handleExport(f.fmt)}>
              {f.label}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
