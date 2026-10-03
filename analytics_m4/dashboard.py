"""Run locally: streamlit run analytics_m4/dashboard.py."""

import json
from pathlib import Path

import streamlit as st

from analyst_m5.core import execute_plan, replay
from analytics_m4.analysis import (
    BUCKETS,
    clock_analysis,
    coverage,
    current_snapshot,
    opening_catalog,
    opening_comparison,
)

PROJECT = Path(__file__).resolve().parents[1]
st.set_page_config(page_title="Chess Analytics Lab", layout="wide")
st.title("Chess Analytics Lab")


@st.cache_data(show_spinner=False)
def figures(snapshot_id):
    snapshot = current_snapshot(PROJECT)
    if snapshot.name != snapshot_id:
        raise ValueError("snapshot changed; refresh the dashboard")
    return (
        coverage(PROJECT, snapshot),
        opening_catalog(PROJECT, snapshot),
        clock_analysis(PROJECT, snapshot),
    )


try:
    snapshot = current_snapshot(PROJECT)
    cover, catalog, clocks = figures(snapshot.name)
except (OSError, ValueError) as exc:
    st.error(f"Checked analytical snapshot unavailable: {exc}")
    st.stop()

date = cover["observed_dates"]
st.caption(
    f"Snapshot {snapshot.name} · observed UTC {date['first_utc_date']} to "
    f"{date['last_utc_date']} · ordered archive prefix · partial source · "
    f"{cover['source_counts']['accepted']:,} accepted games · "
    f"{cover['selection']['selected_games']:,} selected move games"
)
page = st.sidebar.radio(
    "View",
    [
        "Overview and coverage",
        "Opening comparisons",
        "Clock pressure",
        "Data quality",
        "AI analyst",
        "Evaluation results",
    ],
)

if page == "Overview and coverage":
    st.subheader("Observed games and openings")
    st.metric("Complete PGNs", f"{cover['source_counts']['seen']:,}")
    st.metric("Accepted games", f"{cover['source_counts']['accepted']:,}")
    st.metric(
        "Known-opening eligible games", f"{cover['opening_coverage']['known_opening_games']:,}"
    )
    st.bar_chart({row["family"]: row["value"] for row in catalog})
    st.caption(
        "Opening share denominator: known-opening completed eligible games. Source tags only."
    )
    st.warning(
        "The first 100,000 complete games cover one observed day; this is not an August estimate."
    )
elif page == "Opening comparisons":
    st.subheader("Opening score comparison")
    color = st.selectbox("Player color", ["black", "white"])
    band = st.selectbox("Rating band", [(1400, 1600), (1200, 1400), (1600, 1800)])
    base = st.selectbox("Exact base seconds", [60, 180, 300])
    increment = st.selectbox("Exact increment seconds", [0, 2, 3])
    comp = opening_comparison(
        PROJECT,
        snapshot,
        color=color,
        rating_min=band[0],
        rating_max_exclusive=band[1],
        base_seconds=base,
        increment_seconds=increment,
    )
    for family, result in comp["families"].items():
        raw = result["raw"]
        st.write(
            f"**{family}**: {raw['wins']} wins, {raw['draws']} draws, "
            f"{raw['losses']} losses / {raw['eligible_player_games']} games; "
            f"score rate {raw['score_rate']:.1%}"
            if raw["score_rate"] is not None
            else f"**{family}**: no eligible games"
        )
        if result["low_support"]:
            st.warning(f"{family}: fewer than 100 games; low support.")
        st.write(
            "Adjusted score rate and player-cluster interval:",
            result["adjusted_score_rate"],
            result["adjusted_95pct_cluster_bootstrap_interval"],
        )
    st.caption("Common opponent-rating-difference weights; observed association, not causation.")
    st.json(comp["filters"])
elif page == "Clock pressure":
    st.subheader("Exploratory >=200 cp deterioration proxy")
    selected = st.selectbox("Pre-turn clock bucket", BUCKETS)
    row = next(x for x in clocks["buckets"] if x["bucket"] == selected)
    st.write(
        f"{row['proxy_errors']:,} proxy errors / {row['evaluable_moves']:,} "
        f"evaluable moves = {row['error_proxy_rate']:.1%}"
        if row["error_proxy_rate"] is not None
        else "No evaluable moves"
    )
    st.write(
        f"Evaluation coverage: {row['evaluable_moves']:,} / {row['eligible_moves']:,} "
        f"eligible moves = {row['evaluation_coverage']:.1%}"
    )
    st.dataframe([r for r in clocks["strata"] if r["bucket"] == selected], hide_index=True)
    st.warning(
        "Source evaluations are sparse and selected. This does not establish a causal effect."
    )
elif page == "Data quality":
    st.json(cover)
    st.write("Missingness and partial-source status are recorded in the published manifests.")
elif page == "AI analyst":
    st.subheader("Checked analyst — offline")
    mode = st.radio("Input mode", ["Fixture replay", "Typed plan"])
    if mode == "Fixture replay":
        paths = sorted((PROJECT / "evals/replay_plans").glob("*.json"))
        selected_plan = st.selectbox("Recorded fixture plan", paths, format_func=lambda p: p.stem)
        record = json.loads(selected_plan.read_text())
        st.write(record["question"])
        if st.button("Run replay"):
            st.json(replay(PROJECT, record["question"], selected_plan))
    else:
        question = st.text_input("Question", "What share of games used the Sicilian Defense tag?")
        default = {
            "status": "answered",
            "interpretation": "descriptive_observed_prefix",
            "actions": [
                {
                    "tool": "query_metric",
                    "args": {
                        "metric_id": "opening_usage",
                        "filters": {"family": "Sicilian Defense"},
                    },
                }
            ],
        }
        plan_text = st.text_area(
            "Typed reviewed-tool plan (JSON)", json.dumps(default, indent=2), height=180
        )
        if st.button("Run typed plan"):
            try:
                st.json(execute_plan(PROJECT, question, json.loads(plan_text)))
            except (ValueError, OSError) as exc:
                st.error(str(exc))
    st.caption("Evidence IDs refer to this snapshot. Fixture plans are not model responses.")
    st.info(
        "Live provider calls remain disabled pending personal configuration and a spending cap."
    )
else:
    path = PROJECT / "reports/M5-both-harness.json"
    if path.exists():
        report = json.loads(path.read_text())
        st.metric("Fixture replay checks passed", f"{report['passed']} / {report['total']}")
        st.dataframe(
            [{"category": key, **value} for key, value in report["category"].items()],
            hide_index=True,
        )
        st.caption(f"Case set SHA256: {report['case_set_sha256']}")
    st.warning("Harness validation only. No model accuracy or live benchmark is claimed.")
