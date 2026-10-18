"""Write a deterministic Mermaid lineage diagram from a dbt manifest.

Stdlib only. The manifest comes from ``dbt parse`` or ``dbt build``. The
script does not open a warehouse and does not download anything.
"""

import argparse
import json
import sys
from pathlib import Path

LAYERS = (
    "sources",
    "staging",
    "intermediate",
    "marts",
    "semantic_models",
    "metrics",
    "exposures",
)
LAYER_TITLES = {
    "sources": "Sources",
    "staging": "Staging",
    "intermediate": "Intermediate",
    "marts": "Marts",
    "semantic_models": "Semantic models",
    "metrics": "Metrics",
    "exposures": "Exposures",
}
INCLUDED = {"source", "model", "semantic_model", "metric", "exposure"}


def _layer(node: dict) -> str:
    kind = node["resource_type"]
    if kind == "source":
        return "sources"
    if kind == "semantic_model":
        return "semantic_models"
    if kind == "metric":
        return "metrics"
    if kind == "exposure":
        return "exposures"
    folder = str(node.get("path") or "").split("/", 1)[0]
    return {
        "staging": "staging",
        "intermediate": "intermediate",
        "marts": "marts",
    }.get(folder, "other")


def _label(node: dict) -> str:
    kind = node["resource_type"]
    if kind == "source":
        return f"{node['source_name']}.{node['name']}"
    if kind == "semantic_model":
        return f"{node['name']} semantic"
    return str(node["name"])


def _node_id(unique_id: str) -> str:
    safe = "".join(char if char.isalnum() else "_" for char in unique_id)
    return f"n_{safe}"


def _enabled(node: dict) -> bool:
    config = node.get("config")
    return not (isinstance(config, dict) and config.get("enabled") is False)


def _collect(manifest: dict) -> dict[str, dict]:
    pools = (
        manifest.get("sources") or {},
        manifest.get("nodes") or {},
        manifest.get("semantic_models") or {},
        manifest.get("metrics") or {},
        manifest.get("exposures") or {},
    )
    selected = {}
    for pool in pools:
        for unique_id, node in pool.items():
            if node.get("resource_type") not in INCLUDED or not _enabled(node):
                continue
            if node.get("package_name") not in {None, "chess_analytics"}:
                continue
            selected[unique_id] = node
    return selected


def _edges(selected: dict[str, dict]) -> list[tuple[str, str]]:
    edges = []
    for unique_id, node in selected.items():
        depends = node.get("depends_on") or {}
        parents = depends.get("nodes") or []
        for parent in parents:
            if parent in selected:
                edges.append((parent, unique_id))
    return sorted(set(edges))


def render(manifest: dict) -> str:
    """Return the full Markdown document, including the trailing newline."""
    selected = _collect(manifest)
    grouped: dict[str, list[str]] = {layer: [] for layer in (*LAYERS, "other")}
    for unique_id, node in selected.items():
        grouped.setdefault(_layer(node), []).append(unique_id)
    for layer in grouped:
        grouped[layer].sort(key=lambda unique_id: (_label(selected[unique_id]), unique_id))

    lines = [
        "# dbt lineage",
        "",
        "`scripts/render_dbt_dag.py` writes this file from a dbt `manifest.json`.",
        "GitHub renders the diagram below. CI regenerates it and fails if this",
        "copy differs. Arrows point from an upstream node to the node that uses it.",
        "",
        "Semantic-model labels end in `semantic` so they stay distinct from the",
        "view of the same name. Metrics sit on those semantic models. Exposures",
        "are the downstream consumers declared in `dbt/models/exposures.yml`.",
        "",
    ]
    order = [layer for layer in (*LAYERS, "other") if grouped.get(layer)]
    for layer in order:
        title = LAYER_TITLES.get(layer, "Other")
        lines.append(f"- {title}: {len(grouped[layer])}")
    lines.extend(["", "```mermaid", "flowchart TD"])
    for layer in order:
        title = LAYER_TITLES.get(layer, "Other")
        lines.append(f'  subgraph {layer}["{title}"]')
        for unique_id in grouped[layer]:
            label = _label(selected[unique_id]).replace('"', "'")
            lines.append(f'    {_node_id(unique_id)}["{label}"]')
        lines.append("  end")
    for parent, child in _edges(selected):
        lines.append(f"  {_node_id(parent)} --> {_node_id(child)}")
    lines.extend(["```", ""])
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--check",
        action="store_true",
        help="Exit 1 if --output does not already match the manifest.",
    )
    args = parser.parse_args(argv)
    document = render(json.loads(args.manifest.read_text()))
    if args.check:
        current = args.output.read_text() if args.output.is_file() else ""
        if current != document:
            print(
                f"{args.output} is stale. Regenerate it with scripts/render_dbt_dag.py.",
                file=sys.stderr,
            )
            return 1
        return 0
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(document)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
