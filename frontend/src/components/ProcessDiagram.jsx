// Renders the backend-generated process-flow SVG. The SVG is produced
// server-side by the visualizer (BFS layout + swimlanes + elbow routing),
// so the client only needs to mount it.
export default function ProcessDiagram({ svg }) {
  if (!svg) return null;
  return (
    <div className="diagram">
      <div className="diagram-head">
        <span>Process flow</span>
        <span>auto-generated</span>
      </div>
      <div dangerouslySetInnerHTML={{ __html: svg }} />
    </div>
  );
}
