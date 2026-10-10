"""Publication checks: bounded output, preserved evidence and fail-closed source drift."""

import importlib.util
import json
import shutil
from pathlib import Path

import pytest

pytest.importorskip("markdown", reason="Documentation build uses the optional docs extra")
ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("docs_site", ROOT / "scripts/build_docs_site.py")
site = importlib.util.module_from_spec(spec)
spec.loader.exec_module(site)


def test_site_publishes_guides_without_mutating_evidence(tmp_path):
    before = (ROOT / "reports/decisions-routing-comparison.html").read_bytes()
    result = site.build(ROOT, tmp_path / "output")
    assert len(result["pages"]) == 6
    assert result["local_links_checked"] > 50
    assert result["live_requests"] == result["data_downloads"] == 0
    output = tmp_path / "output"
    assert (output / "reports/decisions-routing-comparison.html").read_bytes() == before
    assert (ROOT / "reports/decisions-routing-comparison.html").read_bytes() == before
    assert set(p.name for p in (output / "reports").iterdir()) == {
        "decisions-routing-comparison.html"
    }
    assert not any(".env" in str(p) for p in output.rglob("*"))
    comparison = (output / "comparison.html").read_text()
    assert "24 fresh questions" in comparison and 'id="routing-data"' in comparison
    assert "Known-opening" in (output / "metrics.html").read_text() or (
        "nonempty source opening family" in (output / "metrics.html").read_text()
    )
    assert "uv sync --locked" in (output / "demo.html").read_text()
    site.build(ROOT, output)  # A generated output is safely rebuildable.


def test_publication_rejects_changed_frozen_run(tmp_path):
    for folder in ("reports", "evals/cases"):
        (tmp_path / folder).mkdir(parents=True)
    for name in site.REPORTS:
        shutil.copy2(ROOT / "reports" / name, tmp_path / "reports" / name)
    for name in (
        "jev_routing_v1.tsv",
        "jev_routing_v1_manifest.json",
        "decisions_routing_v1.json",
        "decisions_routing_v1_manifest.json",
    ):
        shutil.copy2(ROOT / "evals/cases" / name, tmp_path / "evals/cases" / name)
    site.routing(tmp_path)
    frozen = tmp_path / "reports/decisions-fresh-pass-1.json"
    obj = json.loads(frozen.read_text())
    obj["predictions"][0]["route"] = "unsupported"
    frozen.write_text(json.dumps(obj))
    with pytest.raises(ValueError, match="Frozen comparison report hash changed"):
        site.routing(tmp_path)


def test_unrelated_output_and_missing_links_are_rejected(tmp_path):
    output = tmp_path / "unrelated"
    output.mkdir()
    note = output / "keep.txt"
    note.write_text("Owner content")
    with pytest.raises(ValueError, match="not a generated site"):
        site.build(ROOT, output)
    assert note.read_text() == "Owner content"
    (output / "index.html").write_text('<a href="missing.html">Missing</a>')
    with pytest.raises(ValueError, match="Broken generated link"):
        site.validate_site(output)
