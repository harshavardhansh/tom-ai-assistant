// The route badge tells the user which "brain" produced the answer:
// GRAPH (process hierarchy), VECTOR (documents), or MULTIHOP (both).
const LABELS = {
  GRAPH: "Graph",
  VECTOR: "Documents",
  MULTIHOP: "Multi-hop",
};

export default function RouteBadge({ route, confidence }) {
  const cls = (route || "VECTOR").toLowerCase();
  return (
    <span className={`badge ${cls}`} title={`Answered via ${LABELS[route] || route}`}>
      <span className="dot" />
      {LABELS[route] || route}
      {typeof confidence === "number" && (
        <span className="confidence">· {Math.round(confidence * 100)}%</span>
      )}
    </span>
  );
}
