"""Process visualizer tests."""
from app.services.visualizer import render_process_svg

LINEAR = {
    "name": "Linear Flow",
    "steps": [
        {"id": "a", "name": "Start", "role": "Role A", "next": ["b"]},
        {"id": "b", "name": "Middle", "role": "Role B", "next": ["c"]},
        {"id": "c", "name": "End", "role": "Role A", "next": []},
    ],
}

BRANCH_LOOP = {
    "name": "Branch and Loop",
    "steps": [
        {"id": "s1", "name": "Receive", "role": "Clerk", "next": ["s2"]},
        {"id": "s2", "name": "Match", "role": "Clerk", "next": ["s3"]},
        {"id": "s3", "name": "OK?", "role": "Clerk", "next": ["s4", "s5"], "labels": ["Yes", "No"]},
        {"id": "s4", "name": "Post", "role": "Clerk", "next": []},
        {"id": "s5", "name": "Fix", "role": "Manager", "next": ["s2"]},
    ],
}


def test_linear_svg():
    svg = render_process_svg(LINEAR)
    assert svg.startswith("<svg")
    assert svg.endswith("</svg>")
    assert "Start" in svg and "End" in svg
    # Two roles -> two swimlane labels.
    assert "Role A" in svg and "Role B" in svg


def test_branch_and_loop_svg():
    svg = render_process_svg(BRANCH_LOOP)
    assert "<polygon" in svg  # decision node renders as a diamond
    assert "Yes" in svg and "No" in svg  # branch labels
    assert svg.count("marker-end") >= 5  # at least one connector per edge


def test_empty_flow():
    assert render_process_svg(None) is None
    svg = render_process_svg({"name": "Empty", "steps": []})
    assert "No process flow" in svg
