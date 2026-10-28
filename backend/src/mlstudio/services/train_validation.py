"""Configuration checks only: no estimators, row sampling, or transformed matrices."""

import math

import numpy as np

from mlstudio.model_catalog import model_parameter_issues
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


def split_issues(split):
    issues = []

    def issue(code, message, field):
        issues.append(PipelineIssue(scope="train", code=code, message=message, field=field))

    if split is None:
        issue("split_missing", "Configure the train/test split in Train.", "split")
        return issues
    if split.test_size is None or not 0.05 <= split.test_size <= 0.5:
        issue("test_size_invalid", "Test size must be between 5% and 50%.", "split.test_size")
    if split.random_seed is None or not 0 <= split.random_seed <= 2147483647:
        issue("seed_invalid", "Experiment seed must be 0 to 2147483647.", "split.random_seed")
    return issues


def regression_train_issues(ir, target):
    issues = model_parameter_issues(ir.model, "regression") + split_issues(ir.split)
    if target is None or ir.split is None:
        return issues
    eligible = int(target.count())
    train, test = partition_sizes(eligible, ir.split)
    if train is None:
        return issues
    if eligible < 3:
        issues.append(
            PipelineIssue(
                scope="train",
                code="eligible_observations",
                field="target.column",
                message="Regression needs at least three non-missing target observations.",
            )
        )
    if train < 2:
        issues.append(
            PipelineIssue(
                scope="train",
                code="split_training_rows",
                field="split.test_size",
                message="The split must leave at least two usable training rows.",
            )
        )
    if test < 1:
        issues.append(
            PipelineIssue(
                scope="train",
                code="split_test_rows",
                field="split.test_size",
                message="The split must leave at least one usable test row.",
            )
        )
    if test < 2:
        issues.append(
            PipelineIssue(
                scope="train",
                code="r2_test_rows",
                field="split.test_size",
                severity="non_blocking",
                message="R² will be unavailable with fewer than two held-out rows.",
            )
        )
    if eligible and target.nunique() == 1:
        issues.append(
            PipelineIssue(
                scope="train",
                code="r2_constant_target",
                field="target.column",
                severity="non_blocking",
                message="The observed target is constant. R² will be unavailable; "
                "a constant target does not invalidate regression configuration.",
            )
        )
    return issues


def train_issues(ir, target):
    if ir.ir_version == "0.2":
        return regression_train_issues(ir, target)
    if ir.ir_version == "0.3":
        from sklearn.model_selection import train_test_split

        issues = model_parameter_issues(ir.model, "multiclass_classification") + split_issues(
            ir.split
        )
        if ir.split is None or target is None or issues:
            return issues
        from mlstudio.code_runtime import MAX_SAMPLES

        if math.ceil(len(target) * ir.split.test_size) > MAX_SAMPLES:
            return [
                *issues,
                PipelineIssue(
                    scope="train",
                    code="multiclass_evaluation_limit",
                    field="split.test_size",
                    message="Multiclass evaluation supports at most 100,000 test rows. "
                    "Reduce the Dataset or test fraction.",
                ),
            ]
        if ir.split.stratify is None:
            return [
                *issues,
                PipelineIssue(
                    scope="train",
                    code="stratify_missing",
                    field="split.stratify",
                    message="Choose whether to stratify by target.",
                ),
            ]
        try:
            if target.isna().any() or not 3 <= target.nunique() <= 50:
                raise ValueError()
            train, test = train_test_split(
                target,
                test_size=ir.split.test_size,
                random_state=ir.split.random_seed,
                stratify=target if ir.split.stratify else None,
            )
            if train.nunique() != target.nunique() or test.nunique() != target.nunique():
                raise ValueError()
        except (ValueError, TypeError):
            issues.append(
                PipelineIssue(
                    scope="train",
                    code="multiclass_split",
                    field="split.test_size",
                    message="Every class must occur in both deterministic partitions. "
                    "Supply at least two rows per class and adjust test size, seed "
                    "or stratification; minority classes are never dropped.",
                )
            )
        return issues
    issues = model_parameter_issues(ir.model, "binary_classification") + split_issues(ir.split)

    def issue(code, message, field):
        issues.append(PipelineIssue(scope="train", code=code, message=message, field=field))

    split = ir.split
    if split is None:
        return issues
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
