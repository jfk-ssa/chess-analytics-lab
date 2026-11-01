"""Train ADR 0116's baseline offline; print holdout metrics, never save weights."""

import argparse
import json
from pathlib import Path
from typing import TypedDict

from chess_analytics.mistake_training import SEED, TrainingRow, feature_matrix, grouped_split


class ReliabilityBin(TypedDict):
    bin: int
    lower: float
    upper: float
    mean_predicted_probability: float | None
    empirical_positive_rate: float | None
    count: int


class Evaluation(TypedDict):
    seed: int
    games: dict[str, list[str]]
    holdout_rows: int
    probabilities: list[float]
    brier_score: float
    reliability: list[ReliabilityBin]


def reliability_table(
    labels: list[bool],
    probabilities: list[float],
    bins: int = 5,
) -> list[ReliabilityBin]:
    """Equal-width bins [lower, upper), with 1.0 included in the final bin."""
    if (
        bins < 1
        or not labels
        or len(labels) != len(probabilities)
        or any(not 0 <= p <= 1 for p in probabilities)
    ):
        raise ValueError("invalid reliability inputs")
    table: list[ReliabilityBin] = []
    for index in range(bins):
        members = [
            (y, p)
            for y, p in zip(labels, probabilities, strict=True)
            if min(int(p * bins), bins - 1) == index
        ]
        count = len(members)
        table.append(
            ReliabilityBin(
                bin=index,
                lower=index / bins,
                upper=(index + 1) / bins,
                count=count,
                mean_predicted_probability=sum(p for _, p in members) / count if count else None,
                empirical_positive_rate=sum(y for y, _ in members) / count if count else None,
            )
        )
    return table


def train_evaluate(rows: list[TrainingRow], seed: int = SEED) -> Evaluation:
    # Optional extra is loaded only when training is explicitly requested.
    from sklearn.calibration import CalibratedClassifierCV
    from sklearn.ensemble import HistGradientBoostingClassifier
    from sklearn.feature_extraction import DictVectorizer
    from sklearn.frozen import FrozenEstimator
    from sklearn.metrics import brier_score_loss
    from sklearn.pipeline import make_pipeline
    from threadpoolctl import threadpool_limits

    development, holdout = grouped_split(rows, seed=seed)
    training, calibration = grouped_split(development, test_fraction=1 / 3, seed=seed)
    for name, part in (("training", training), ("calibration", calibration)):
        if {row["error_proxy"] for row in part} != {False, True}:
            raise ValueError(f"{name} games must contain both label classes")
    labels = [row["error_proxy"] for row in holdout]
    with threadpool_limits(limits=1):
        model = make_pipeline(
            DictVectorizer(sparse=False),
            HistGradientBoostingClassifier(
                random_state=seed,
                early_stopping=False,
                max_iter=40,
                min_samples_leaf=2,
            ),
        )
        model.fit(feature_matrix(training), [row["error_proxy"] for row in training])
        calibrated = CalibratedClassifierCV(FrozenEstimator(model), method="sigmoid", cv=2)
        calibrated.fit(feature_matrix(calibration), [row["error_proxy"] for row in calibration])
        probabilities = calibrated.predict_proba(feature_matrix(holdout))[:, 1].tolist()
    return {
        "seed": seed,
        "games": {
            name: sorted({row["game_id"] for row in part})
            for name, part in (
                ("training", training),
                ("calibration", calibration),
                ("holdout", holdout),
            )
        },
        "holdout_rows": len(labels),
        "probabilities": probabilities,
        "brier_score": float(brier_score_loss(labels, probabilities)),
        "reliability": reliability_table(labels, probabilities),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("frame", type=Path)
    args = parser.parse_args()
    payload = json.loads(args.frame.read_text())
    rows = payload["training_frame"] if isinstance(payload, dict) else payload
    print(json.dumps(train_evaluate(rows), indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
