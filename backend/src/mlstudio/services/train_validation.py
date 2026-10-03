"""Configuration checks only: no estimators, row sampling, or transformed matrices."""

import math

import numpy as np

from mlstudio.pipeline_schemas import PipelineIssue


def partition_sizes(rows, split):
    if split is None or split.test_size is None or not 0.05 <= split.test_size <= 0.5:
        return None, None
    test = math.ceil(rows * split.test_size)
    return rows - test, test


def stratified_train_counts(counts, train_rows, seed):
    """Binary largest-remainder counts, with sklearn-compatible seeded tie breaking.

    Counts are in sorted class order. This inspects allocation, never row indices.
    sklearn StratifiedShuffleSplit allocates training counts first; the test set
    receives the remainder when train_size is unspecified. Source reference:
    sklearn/model_selection/_split.py and sklearn/utils/extmath.py.
    """
    counts = np.asarray(counts, dtype=int)
    expected = counts / counts.sum() * train_rows
    allocation = np.floor(expected).astype(int)
    if allocation.sum() < train_rows:
        remainders = expected - allocation
        tied = np.flatnonzero(remainders == remainders.max())
        winner = np.random.RandomState(seed).choice(tied, size=1, replace=False)[0]
        allocation[winner] += 1
    return allocation


def train_issues(ir, target):
    issues = []

    def issue(code, message, field):
        issues.append(PipelineIssue(scope="train", code=code, message=message, field=field))

    if ir.model is None:
        issue("model_missing", "Select a model in Train.", "model")
    else:
        for name, value in ir.model.parameters.model_dump().items():
            if name == "max_depth" and value is None:
                continue
            if name == "penalty":
                valid = value in {"l1", "l2"}
                requirement = "Choose l1 or l2."
            elif name == "C":
                valid = value is not None and value > 0
                requirement = "C must be finite and greater than zero."
            else:
                minimum = 2 if name == "min_samples_split" else 1
                valid = value is not None and value >= minimum
                requirement = f"{name} must be an integer of at least {minimum}."
            if not valid:
                issue("model_parameter", requirement, f"model.parameters.{name}")
    split = ir.split
    if split is None:
        issue("split_missing", "Configure the train/test split in Train.", "split")
        return issues
    if split.test_size is None or not 0.05 <= split.test_size <= 0.5:
        issue("test_size_invalid", "Test size must be between 5% and 50%.", "split.test_size")
    if split.random_seed is None or not 0 <= split.random_seed <= 2147483647:
        issue("seed_invalid", "Experiment seed must be 0 to 2147483647.", "split.random_seed")
    if split.stratify is None:
        issue("stratify_missing", "Choose whether to stratify by target.", "split.stratify")
    if target is None or target.nunique() != 2:
        return issues
    train, test = partition_sizes(int(target.count()), split)
    if train is None:
        return issues
    if train < 1 or test < 1:
        issue("split_empty", "The split must leave usable rows in both partitions.", "split")
    if split.stratify:
        counts = target.dropna().value_counts().sort_index().to_numpy()
        if min(counts) < 2:
            issue(
                "stratify_class_count",
                "A target class has only one usable row; stratification "
                "requires at least two per class.",
                "split.stratify",
            )
        elif train < 2 or test < 2:
            issue(
                "stratify_partition",
                f"This split produces {train} training and {test} test "
                "rows. Each stratified partition needs at least two rows.",
                "split.test_size",
            )
        elif split.random_seed is not None and 0 <= split.random_seed <= 2147483647:
            allocated = stratified_train_counts(counts, train, split.random_seed)
            if min(allocated) < 1 or min(counts - allocated) < 1:
                issue(
                    "stratify_allocation",
                    "The requested proportion and seed leave a target "
                    "class absent from a partition after integer stratified allocation. "
                    "Adjust the split or explicitly disable stratification.",
                    "split.test_size",
                )
    return issues
