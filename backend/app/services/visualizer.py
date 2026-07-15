"""Process-flow visualizer (POC gotcha #2: BFS positioning + swimlanes + elbow routing).

Input  : flow dict {"name", "steps":[{"id","name","role","next":[...], "labels":[...]?}]}
Output : a self-contained SVG string (no external diagramming tools).

Layout:
  - Columns (x) = BFS rank from the start step(s); back-edges are treated as loops.
  - Swimlanes (y) = one horizontal band per role, in order of first appearance.
  - Steps with >1 outgoing edge render as decision diamonds; others as rounded boxes.
  - Connectors are orthogonal (elbow); loop edges route through a channel below the lanes.
"""
from __future__ import annotations

from collections import defaultdict, deque
from html import escape
from typing import Any, Optional

# Geometry
_COL_W = 220
_LANE_H = 120
_BOX_W = 150
_BOX_H = 54
_MARGIN_L = 160  # space for lane labels
_MARGIN_T = 50
_PAD = 30

# A restrained, professional palette (KPMG-leaning blues).
_LANE_FILLS = ["#EAF0F8", "#F2F6FB", "#E8F4F1", "#F4F0F7", "#FBF3EA"]
_BOX_FILL = "#FFFFFF"
_BOX_STROKE = "#1A2B5E"
_DECISION_FILL = "#FFF6E5"
_DECISION_STROKE = "#B7791F"
_EDGE = "#5B6B8C"
_TEXT = "#10203F"


class ProcessVisualizer:
    def render_svg(self, flow: dict[str, Any]) -> str:
        steps: list[dict[str, Any]] = flow.get("steps", [])
        if not steps:
            return self._empty_svg(flow.get("name", "Process"))

        by_id = {s["id"]: s for s in steps}
        adjacency = {s["id"]: list(s.get("next", [])) for s in steps}
        ranks = self._bfs_ranks(steps, adjacency)
        lanes, lane_order = self._assign_lanes(steps)

        # Position: stack nodes that share the same (rank, lane) cell.
        cell_members: dict[tuple[int, int], list[str]] = defaultdict(list)
        for s in steps:
            cell_members[(ranks[s["id"]], lanes[s["id"]])].append(s["id"])

        pos: dict[str, tuple[float, float]] = {}
        for (rank, lane), members in cell_members.items():
            for offset, node_id in enumerate(members):
                cx = _MARGIN_L + rank * _COL_W + _COL_W / 2
                base_y = _MARGIN_T + lane * _LANE_H + _LANE_H / 2
                cy = base_y + (offset - (len(members) - 1) / 2) * (_BOX_H + 14)
                pos[node_id] = (cx, cy)

        max_rank = max(ranks.values())
        width = _MARGIN_L + (max_rank + 1) * _COL_W + _PAD
        height = _MARGIN_T + len(lane_order) * _LANE_H + 60  # +channel for loops
        loop_channel_y = _MARGIN_T + len(lane_order) * _LANE_H + 24

        parts: list[str] = []
        parts.append(
            f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" '
            f'font-family="Segoe UI, Arial, sans-serif" role="img" '
            f'aria-label="Process flow: {escape(flow.get("name",""))}">'
        )
        parts.append(self._defs())
        parts.append(
            f'<text x="{_MARGIN_L}" y="28" font-size="18" font-weight="700" '
            f'fill="{_TEXT}">{escape(flow.get("name","Process flow"))}</text>'
        )
        # Swimlane bands + labels
        for i, role in enumerate(lane_order):
            y = _MARGIN_T + i * _LANE_H
            fill = _LANE_FILLS[i % len(_LANE_FILLS)]
            parts.append(f'<rect x="0" y="{y}" width="{width}" height="{_LANE_H}" fill="{fill}"/>')
            parts.append(
                f'<text x="12" y="{y + _LANE_H/2}" font-size="13" font-weight="600" '
                f'fill="{_TEXT}" dominant-baseline="middle">{escape(role)}</text>'
            )
            parts.append(f'<line x1="{_MARGIN_L}" y1="{y}" x2="{width}" y2="{y}" stroke="#D5DCEA"/>')
        parts.append(
            f'<line x1="{_MARGIN_L}" y1="{_MARGIN_T + len(lane_order)*_LANE_H}" '
            f'x2="{width}" y2="{_MARGIN_T + len(lane_order)*_LANE_H}" stroke="#D5DCEA"/>'
        )

        # Edges first (so nodes sit on top)
        for node_id, targets in adjacency.items():
            labels = by_id[node_id].get("labels", [])
            for j, tgt in enumerate(targets):
                if tgt not in pos:
                    continue
                forward = ranks[tgt] > ranks[node_id]
                label = labels[j] if j < len(labels) else None
                parts.append(self._edge(pos[node_id], pos[tgt], forward, loop_channel_y, label))

        # Nodes
        for s in steps:
            cx, cy = pos[s["id"]]
            is_decision = len(adjacency[s["id"]]) > 1
            parts.append(self._node(cx, cy, s["name"], is_decision))

        parts.append("</svg>")
        return "".join(parts)

    # -- layout helpers -------------------------------------------------
    def _bfs_ranks(self, steps: list[dict], adjacency: dict[str, list[str]]) -> dict[str, int]:
        indeg: dict[str, int] = defaultdict(int)
        for src, tgts in adjacency.items():
            for t in tgts:
                indeg[t] += 1
        starts = [s["id"] for s in steps if indeg[s["id"]] == 0] or [steps[0]["id"]]
        ranks: dict[str, int] = {sid: 0 for sid in starts}
        queue = deque(starts)
        seen = set(starts)
        while queue:
            node = queue.popleft()
            for nxt in adjacency.get(node, []):
                cand = ranks[node] + 1
                if nxt not in ranks or cand > ranks[nxt]:
                    # forward layering; ignore back-edges to avoid runaway loops
                    if nxt not in seen or cand > ranks.get(nxt, 0):
                        ranks[nxt] = max(ranks.get(nxt, 0), cand) if nxt in seen else cand
                if nxt not in seen:
                    seen.add(nxt)
                    queue.append(nxt)
        for s in steps:  # any unreached node
            ranks.setdefault(s["id"], 0)
        return ranks

    def _assign_lanes(self, steps: list[dict]) -> tuple[dict[str, int], list[str]]:
        order: list[str] = []
        for s in steps:
            role = s.get("role", "Unassigned")
            if role not in order:
                order.append(role)
        lane_of = {s["id"]: order.index(s.get("role", "Unassigned")) for s in steps}
        return lane_of, order

    # -- drawing helpers ------------------------------------------------
    def _defs(self) -> str:
        return (
            '<defs><marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" '
            'markerWidth="7" markerHeight="7" orient="auto-start-reverse">'
            f'<path d="M0,0 L10,5 L0,10 z" fill="{_EDGE}"/></marker></defs>'
        )

    def _node(self, cx: float, cy: float, name: str, is_decision: bool) -> str:
        text = self._wrap(name)
        lines = text.split("\n")
        tspans = "".join(
            f'<tspan x="{cx}" dy="{0 if i == 0 else 14}">{escape(line)}</tspan>'
            for i, line in enumerate(lines)
        )
        ty = cy - (len(lines) - 1) * 7
        if is_decision:
            half_w, half_h = _BOX_W / 2 + 6, _BOX_H / 2 + 8
            diamond = (
                f'{cx},{cy-half_h} {cx+half_w},{cy} {cx},{cy+half_h} {cx-half_w},{cy}'
            )
            shape = (
                f'<polygon points="{diamond}" fill="{_DECISION_FILL}" '
                f'stroke="{_DECISION_STROKE}" stroke-width="1.5"/>'
            )
        else:
            shape = (
                f'<rect x="{cx-_BOX_W/2}" y="{cy-_BOX_H/2}" width="{_BOX_W}" height="{_BOX_H}" '
                f'rx="8" ry="8" fill="{_BOX_FILL}" stroke="{_BOX_STROKE}" stroke-width="1.5"/>'
            )
        return (
            f'{shape}<text x="{cx}" y="{ty}" font-size="12" fill="{_TEXT}" '
            f'text-anchor="middle" dominant-baseline="middle">{tspans}</text>'
        )

    def _edge(self, src, tgt, forward, channel_y, label) -> str:
        sx, sy = src
        tx, ty = tgt
        if forward:
            start_x = sx + _BOX_W / 2
            end_x = tx - _BOX_W / 2
            midx = (start_x + end_x) / 2
            d = f"M{start_x},{sy} H{midx} V{ty} H{end_x}"
        else:  # loop / back-edge: route through the channel below the lanes
            start_x = sx
            end_x = tx
            d = (
                f"M{start_x},{sy + _BOX_H/2} V{channel_y} "
                f"H{end_x} V{ty + _BOX_H/2}"
            )
        path = f'<path d="{d}" fill="none" stroke="{_EDGE}" stroke-width="1.6" marker-end="url(#arrow)"/>'
        if label:
            lx = (sx + tx) / 2
            ly = (sy + ty) / 2 - 6 if forward else channel_y - 6
            path += (
                f'<rect x="{lx-16}" y="{ly-11}" width="32" height="16" rx="3" fill="#FFFFFF" '
                f'stroke="#D5DCEA"/><text x="{lx}" y="{ly}" font-size="10" fill="{_TEXT}" '
                f'text-anchor="middle" dominant-baseline="middle">{escape(str(label))}</text>'
            )
        return path

    def _wrap(self, text: str, width: int = 18) -> str:
        words = text.split()
        lines, current = [], ""
        for w in words:
            if len(current) + len(w) + 1 <= width:
                current = f"{current} {w}".strip()
            else:
                lines.append(current)
                current = w
        if current:
            lines.append(current)
        return "\n".join(lines[:3])

    def _empty_svg(self, name: str) -> str:
        return (
            f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 400 80">'
            f'<text x="10" y="40" font-size="13" fill="{_TEXT}">'
            f'No process flow available for {escape(name)}.</text></svg>'
        )


def render_process_svg(flow: Optional[dict[str, Any]]) -> Optional[str]:
    if not flow:
        return None
    return ProcessVisualizer().render_svg(flow)
