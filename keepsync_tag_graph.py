"""Label co-occurrence graph helpers."""

from collections import Counter, defaultdict
from dataclasses import dataclass
from itertools import combinations
from typing import Dict, Iterable, List, Tuple

from keepsync_models import Note


@dataclass(frozen=True)
class TagNode:
    label: str
    count: int


@dataclass(frozen=True)
class TagEdge:
    left: str
    right: str
    count: int
    note_ids: Tuple[str, ...]


@dataclass(frozen=True)
class TagGraph:
    nodes: Tuple[TagNode, ...]
    edges: Tuple[TagEdge, ...]


def normalized_note_labels(labels: Iterable[str]) -> Tuple[str, ...]:
    return tuple(sorted({str(label or "").strip() for label in labels or [] if str(label or "").strip()}))


def build_tag_graph(notes: Iterable[Note]) -> TagGraph:
    node_counts: Counter[str] = Counter()
    edge_counts: Dict[Tuple[str, str], int] = defaultdict(int)
    edge_note_ids: Dict[Tuple[str, str], set[str]] = defaultdict(set)

    for note in notes:
        labels = normalized_note_labels(note.labels)
        node_counts.update(labels)
        for left, right in combinations(labels, 2):
            edge_counts[(left, right)] += 1
            edge_note_ids[(left, right)].add(note.id)

    nodes = tuple(
        TagNode(label=label, count=count)
        for label, count in sorted(node_counts.items(), key=lambda item: (-item[1], item[0].lower()))
    )
    edges = tuple(
        TagEdge(left=left, right=right, count=count, note_ids=tuple(sorted(edge_note_ids[(left, right)])))
        for (left, right), count in sorted(
            edge_counts.items(),
            key=lambda item: (-item[1], item[0][0].lower(), item[0][1].lower()),
        )
    )
    return TagGraph(nodes=nodes, edges=edges)


def tag_graph_summary_lines(graph: TagGraph, limit: int = 40) -> List[str]:
    if not graph.nodes:
        return ["No labeled notes yet."]

    lines = ["Labels"]
    for node in graph.nodes[:limit]:
        lines.append(f"- {node.label}: {node.count} note{'s' if node.count != 1 else ''}")

    lines.append("")
    lines.append("Shared Labels")
    if not graph.edges:
        lines.append("- No shared label pairs yet.")
        return lines

    for edge in graph.edges[:limit]:
        lines.append(f"- {edge.left} + {edge.right}: {edge.count} note{'s' if edge.count != 1 else ''}")
    return lines
