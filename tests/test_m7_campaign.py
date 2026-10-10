"""Offline checks that the consolidated M7 command still describes frozen cases."""

import json
from pathlib import Path

import pytest

from chess_analytics.cli import main
from chess_analytics.m7_campaign import campaign_by_id, load_campaigns, question_rows

PROJECT = Path(__file__).resolve().parents[1]


def test_every_campaign_matches_frozen_case_wording():
    for campaign in load_campaigns(PROJECT):
        cases = json.loads((PROJECT / campaign["case"]).read_text())
        assert question_rows(campaign) == [(case["id"], case["question"]) for case in cases]


def test_pinned_sources_keep_recorded_prefix_hashes():
    campaigns = {item["id"]: item for item in load_campaigns(PROJECT)}
    july = campaigns["july"]["source"]
    december = campaigns["december"]["source"]
    assert july["period"] == "2026-07"
    assert july["compressed_prefix_sha256"].startswith("126392ad")
    assert december["period"] == "2025-12"
    assert december["url"].endswith("lichess_db_standard_rated_2025-12.pgn.zst")
    assert all(
        item["source"] is None for item in campaigns.values() if item["id"].startswith("holdout-")
    )


def test_unknown_campaign_is_rejected():
    with pytest.raises(SystemExit):
        main(["m7", "--campaign", "not-a-month", "pin"])


def test_december_campaign_is_addressable():
    campaign = campaign_by_id(PROJECT, "december")
    assert campaign["check"]["sandbox"]
    assert campaign["case"] == "evals/cases/m7_holdout_v12.json"
