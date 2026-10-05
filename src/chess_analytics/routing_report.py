"""Standalone, dependency-free HTML comparison of frozen routing results."""

# HTML/CSS template lines are intentionally kept intact.
# ruff: noqa: E501

import argparse
import html
import json
from pathlib import Path

from chess_analytics.routing_study import LABELS


def _escape(value) -> str:
    return html.escape(str(value), quote=True)


def _matrix(scoring: dict) -> str:
    rows = scoring["confusion"]
    head = "".join(f"<th>{_escape(label)}</th>" for label in (*LABELS, "fallback"))
    body = []
    for truth in LABELS:
        cells = "".join(
            f'<td class="{"hit" if truth == predicted else ""}">{rows[truth][predicted]}</td>'
            for predicted in (*LABELS, "fallback")
        )
        body.append(f"<tr><th>{_escape(truth)}</th>{cells}</tr>")
    return f'<div class="scroll"><table><thead><tr><th>True route ↓ / predicted →</th>{head}</tr></thead><tbody>{"".join(body)}</tbody></table></div>'


def _curve(scoring: dict) -> str:
    points = scoring.get("selective_curve")
    if not points:
        return "<p>Probability threshold curve awaits actual Jev responses.</p>"
    plotted = [p for p in points if p["error_rate_among_accepted"] is not None]
    positions = " ".join(
        f"{50 + 500 * p['coverage']:.1f},{225 - 180 * p['error_rate_among_accepted']:.1f}"
        for p in plotted
    )
    cells = "".join(
        "<tr>"
        f"<td>{p['threshold']:.2f}</td>"
        f"<td>{p['accepted']}/{scoring['cases']}</td>"
        f"<td>{p['errors']}</td>"
        f"<td>{'—' if p['error_rate_among_accepted'] is None else format(p['error_rate_among_accepted'], '.1%')}</td>"
        "</tr>"
        for p in points
    )
    svg = (
        '<svg viewBox="0 0 600 270" role="img" aria-label="Coverage versus error rate">'
        '<line x1="50" y1="225" x2="550" y2="225" stroke="#697386"/>'
        '<line x1="50" y1="45" x2="50" y2="225" stroke="#697386"/>'
        '<text x="280" y="258">Auto-route coverage →</text>'
        '<text x="58" y="35">Error among auto-routed ↑</text>'
        f'<polyline fill="none" stroke="#54d5af" stroke-width="3" points="{positions}"/>'
        "</svg>"
    )
    return (
        "<h3>Selective routing</h3>"
        "<p>Lower probability thresholds route more questions automatically. "
        "The cost of every Jev call remains in the total, including fallbacks.</p>"
        f"{svg}<table><thead><tr><th>Threshold</th><th>Accepted</th><th>Errors</th>"
        f"<th>Error rate</th></tr></thead><tbody>{cells}</tbody></table>"
    )


def _panel(name: str, report: dict | None, *, actual_kind: str) -> str:
    if report is None:
        return f'<section><h2>{_escape(name)}</h2><p class="pending">Awaiting actual evaluation.</p></section>'
    if report.get("transport_kind") == "injected_mock":
        return f'<section><h2>{_escape(name)}</h2><p class="pending">Mock transport is harness evidence only.</p></section>'
    if report.get("kind") == actual_kind and actual_kind != "m8_rules_routing_results":
        if not report.get("complete"):
            return (
                f'<section><h2>{_escape(name)}</h2><p class="pending">Stopped after '
                f"{report.get('completed_cases', 0)}/{report.get('total_cases', 0)} cases. "
                "Failure and cost reservation remain in the attempt report; no full score.</p></section>"
            )
        scoring = report["scoring"]
        cost = report["accounted_gross_usd"]
        details = (
            f"{scoring['correct']}/{scoring['cases']} correct · "
            f"unsupported recall {scoring['unsupported_recall']:.0%} · "
            f"gross ${cost:.6f} · "
            f"${cost / scoring['correct']:.6f} per correct route"
            if scoring["correct"]
            else f"0/{scoring['cases']} correct · gross ${cost:.6f}"
        )
        return (
            f'<section><h2>{_escape(name)}</h2><p class="stat">{details}</p>'
            f"{_matrix(scoring)}{_curve(scoring) if name.startswith('Jev Choice') else ''}</section>"
        )
    if report.get("kind") != "m8_rules_routing_results":
        raise ValueError("unexpected routing report kind")
    scoring = report
    return (
        f"<section><h2>{_escape(name)}</h2>"
        f'<p class="stat">{scoring["correct"]}/{scoring["cases"]} correct · '
        f"unsupported recall {scoring['unsupported_recall']:.0%}</p>"
        f"{_matrix(scoring)}</section>"
    )


def _hybrid(jev: dict | None, analyst: dict | None, rules: dict, name: str) -> str:
    """Replay Jev-first routes with observed analyst per-case fallback costs."""
    if not jev or not analyst or not jev.get("complete") or not analyst.get("complete"):
        return ""
    if jev.get("transport_kind") != "typesafe_api" or analyst.get("transport_kind") != "openai_api":
        return ""
    truth = rules["references"]
    analyst_by_id = {item["id"]: item for item in analyst["predictions"]}
    if set(analyst_by_id) != set(truth) or {item["id"] for item in jev["predictions"]} != set(
        truth
    ):
        raise ValueError("hybrid inputs do not share case identities")
    rows = []
    for threshold in (0.0, 0.5, 0.7, 0.85, 0.95):
        accepted = 0
        correct = 0
        fallback_cost = 0.0
        for prediction in jev["predictions"]:
            confidence = prediction["probabilities"][prediction["route"]]
            use_jev = confidence >= threshold
            accepted += use_jev
            route = prediction["route"] if use_jev else analyst_by_id[prediction["id"]]["route"]
            if not use_jev:
                fallback_cost += analyst_by_id[prediction["id"]]["gross_cost_usd"]
            correct += route == truth[prediction["id"]]
        gross = jev["accounted_gross_usd"] + fallback_cost
        rows.append(
            f"<tr><td>{threshold:.2f}</td><td>{accepted}/{len(truth)}</td>"
            f"<td>{correct}/{len(truth)}</td><td>${gross:.6f}</td>"
            f"<td>${gross / correct:.6f}</td></tr>"
            if correct
            else f"<tr><td>{threshold:.2f}</td><td>{accepted}/{len(truth)}</td>"
            f"<td>0/{len(truth)}</td><td>${gross:.6f}</td><td>—</td></tr>"
        )
    return (
        f"<section><h2>{_escape(name)} with analyst fallback</h2>"
        "<p>Post hoc replay: Jev cost for every question plus observed analyst cost "
        "for cases below the threshold. This combined path was not executed; "
        "cache cost and latency could differ. Correctness is for routes, not final answers.</p>"
        "<table><thead><tr><th>Jev threshold</th><th>Jev routes</th><th>Correct routes</th>"
        "<th>Gross</th><th>Gross/correct route</th></tr></thead><tbody>"
        + "".join(rows)
        + "</tbody></table></section>"
    )


def _repeat_summary(first: dict | None, repeat: dict | None) -> str:
    if not first or not repeat or not first.get("complete") or not repeat.get("complete"):
        return ""
    if (
        first.get("transport_kind") != "typesafe_api"
        or repeat.get("transport_kind") != "typesafe_api"
    ):
        return ""
    by_id = {item["id"]: item["route"] for item in repeat["predictions"]}
    if {item["id"] for item in first["predictions"]} != set(by_id):
        raise ValueError("Jev repetitions do not share case identities")
    changes = [item["id"] for item in first["predictions"] if item["route"] != by_id[item["id"]]]
    return (
        '<section><h2>Repeatability</h2><p class="stat">'
        f"{len(changes)}/{len(by_id)} routes changed between identical frozen requests."
        "</p><p>Changed case IDs: "
        f"{_escape(', '.join(changes) if changes else 'none')}. "
        "Two passes on a small fixed set do not establish future stability.</p></section>"
    )


def render(
    rules: dict,
    jev: dict | None = None,
    analyst: dict | None = None,
    jev_repeat: dict | None = None,
) -> str:
    digest = rules["case_sha256"]
    if rules.get("split") != "test":
        raise ValueError("portfolio display requires the frozen test split")
    for report in (jev, analyst, jev_repeat):
        if report is not None and (
            report.get("split") != "test" or report.get("case_sha256") != digest
        ):
            raise ValueError("comparison reports do not share the frozen test cases")
    content = (
        _panel("Rules baseline", rules, actual_kind="m8_rules_routing_results")
        + _panel(
            "Existing structured analyst",
            analyst,
            actual_kind="m8_existing_structured_analyst_attempt",
        )
        + _panel("Jev Choice · pass 1", jev, actual_kind="m8_jev_live_attempt")
        + (
            _panel("Jev Choice · pass 2", jev_repeat, actual_kind="m8_jev_live_attempt")
            if jev_repeat is not None
            else ""
        )
        + _repeat_summary(jev, jev_repeat)
        + _hybrid(jev, analyst, rules, "Pass 1")
        + _hybrid(jev_repeat, analyst, rules, "Pass 2")
    )
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Chess Analytics Lab · routing study</title>
<style>
:root {{ color-scheme: dark; font-family: system-ui, sans-serif; background: #101923; color: #e8eff2; }}
body {{ max-width: 1180px; margin: 0 auto; padding: 2rem; }}
h1 {{ font-size: 2rem; }} h2 {{ color: #54d5af; }} section {{ background: #172532; border: 1px solid #304250; border-radius: 12px; margin: 1.4rem 0; padding: 1.3rem; }}
p {{ line-height: 1.5; }} .lede {{ max-width: 850px; color: #b8cbd4; }} .stat {{ font-weight: 650; }} .pending {{ color: #f5c66c; }}
.scroll {{ overflow-x: auto; }} table {{ border-collapse: collapse; font-size: .81rem; margin: 1rem 0; }} th, td {{ padding: .4rem .55rem; border: 1px solid #38505e; text-align: right; }} th:first-child {{ text-align: left; }} .hit {{ background: #245545; }} svg {{ max-width: 580px; width: 100%; }}
</style></head><body>
<h1>Question-routing study</h1>
<p class="lede">One new, manually authored 40-question test split, balanced across eight routes. Rows are true labels and columns are predicted routes. This compares semantic routing, not numerical chess answers or general model accuracy. The labels were authored before these model runs but have not been independently human adjudicated.</p>
<p>Frozen case SHA-256: <code>{_escape(digest)}</code></p>
{content}
<p class="lede">Panel costs are for each complete pass. The separate <a href="M8-routing-checkpoint.json">checkpoint</a> includes the stopped analyst attempt in cumulative gross cost. The analyst ran checked tools against the synthetic demo snapshot; routing labels judge question intent, not whether its openings occur in that snapshot. Full raw attempts remain in ignored local work, and mocked responses never appear as live evidence.</p>
</body></html>"""


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Render the frozen M8 routing comparison")
    parser.add_argument("--rules", type=Path, required=True)
    parser.add_argument("--jev", type=Path)
    parser.add_argument("--jev-repeat", type=Path)
    parser.add_argument("--analyst", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        rules = json.loads(args.rules.read_text())
        jev = json.loads(args.jev.read_text()) if args.jev else None
        jev_repeat = json.loads(args.jev_repeat.read_text()) if args.jev_repeat else None
        analyst = json.loads(args.analyst.read_text()) if args.analyst else None
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(render(rules, jev, analyst, jev_repeat))
        print(args.output)
        return 0
    except (OSError, ValueError, KeyError) as exc:
        parser.exit(1, f"routing report: {exc}\n")


if __name__ == "__main__":
    raise SystemExit(main())
