"""New standalone checks embedded only in the multiclass generator."""

HELPERS = """def validate_multiclass_target(target, labels):
    if target.isna().any():
        raise WorkloadValidationError('Multiclass target cannot contain missing labels.')
    expected = multiclass_labels(labels)
    observed = [scalar_record(v) for v in target.unique()]
    if len(observed) != len(expected) or any(v not in expected for v in observed):
        raise WorkloadValidationError('Multiclass target differs from the resolved class universe.')
    if type_of_target(target) != 'multiclass':
        raise WorkloadValidationError('Unsupported continuous, mixed or multilabel target.')


def validate_multiclass_partition(features, training, test, labels):
    if training.nunique() != len(labels) or test.nunique() != len(labels):
        raise WorkloadValidationError(
            'Every target class must occur in both partitions. Review split settings.')
    if features.isna().all().any():
        raise WorkloadValidationError('A training feature has no observed values.')
"""
