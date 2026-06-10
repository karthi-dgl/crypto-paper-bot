"""
Walk-forward training. The model is ALWAYS evaluated on months it has never seen.

Usage:  python train.py
Outputs: model.pkl (final model, trained on all data)
         oos_predictions.csv (honest out-of-sample probabilities for backtest_ai.py)
"""
import pickle

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier

from features import load_dataset, HORIZON

MIN_TRAIN_MONTHS = 6
PURGE = HORIZON + 1          # gap between train and test to stop label leakage


SEEDS = (42, 7, 2026)        # v2: ensemble of 3 models, probabilities averaged


def make_model(seed=42):
    return HistGradientBoostingClassifier(
        max_iter=400, learning_rate=0.05, max_depth=6,
        min_samples_leaf=200, l2_regularization=1.0,
        class_weight="balanced", random_state=seed)


def fit_ensemble(X, y):
    return [make_model(s).fit(X, y) for s in SEEDS]


def proba_ensemble(models, X):
    return np.mean([m.predict_proba(X) for m in models], axis=0)


def walk_forward(X, y, meta):
    month = pd.to_datetime(meta.time, unit="s").dt.to_period("M")
    months = sorted(month.unique())
    if len(months) <= MIN_TRAIN_MONTHS:
        raise SystemExit(f"Need > {MIN_TRAIN_MONTHS} months of data; got {len(months)}. "
                         "Run fetch_data.py with more days.")
    rows = []
    for k in range(MIN_TRAIN_MONTHS, len(months)):
        test_mask = (month == months[k]).values
        train_idx = np.where(month < months[k])[0]
        train_idx = train_idx[:-PURGE] if len(train_idx) > PURGE else train_idx
        models = fit_ensemble(X.iloc[train_idx], y[train_idx])
        proba = proba_ensemble(models, X.iloc[np.where(test_mask)[0]])
        cls = list(models[0].classes_)
        p = np.zeros((proba.shape[0], 3))
        for ci, cl in enumerate(cls):
            p[:, int(cl)] = proba[:, ci]
        sub = meta[test_mask].copy()
        sub["p_none"], sub["p_long"], sub["p_short"] = p[:, 0], p[:, 1], p[:, 2]
        sub["y"] = y[test_mask]
        rows.append(sub)
        hit = (np.argmax(p, axis=1) == y[test_mask]).mean()
        print(f"  fold {months[k]}: trained on {len(train_idx):,} bars, "
              f"test {test_mask.sum():,} bars, raw accuracy {hit:.2%}")
    return pd.concat(rows, ignore_index=True)


if __name__ == "__main__":
    print("Loading data and building 30+ features (takes a minute)...")
    X, y, meta = load_dataset()
    dist = pd.Series(y).value_counts(normalize=True)
    print(f"{len(X):,} bars | labels: none {dist.get(0, 0):.0%}, "
          f"long-wins {dist.get(1, 0):.0%}, short-wins {dist.get(2, 0):.0%}")

    print("\nWalk-forward validation:")
    oos = walk_forward(X, y, meta)
    oos.to_csv("oos_predictions.csv", index=False)
    print(f"\nSaved {len(oos):,} out-of-sample predictions -> oos_predictions.csv")

    print("Training final ensemble on ALL data for live use...")
    final = fit_ensemble(X, y)
    with open("model.pkl", "wb") as fh:
        pickle.dump({"model": final, "features": list(X.columns)}, fh)
    print("Saved model.pkl")
    print("\nNext:  python backtest_ai.py   (simulates Rs 50,000 on the unseen months)")
