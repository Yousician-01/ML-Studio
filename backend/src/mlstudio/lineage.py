"""Computed feature provenance and fixed-stage admission, never execution/scheduling."""


def references(expression):
    if not expression:
        return []
    if expression.get("kind") in {"column", "reference"}:
        return [expression["name"]]
    return [name for arg in expression.get("arguments", []) for name in references(arg)]


def registry(ir, columns):
    ir = ir.model_dump(mode="json") if hasattr(ir, "model_dump") else ir
    nodes, issues, operations = {}, [], []
    target = (ir.get("target") or {}).get("column")
    schema = {c["name"]: c for c in columns}

    def issue(code, name, message):
        issues.append({"code": code, "column": name, "message": message})

    def add(name, origin, stage, deps, fitted=False, semantic="unknown", producer=None):
        if name in nodes:
            issue("output_collision", name, f'Output "{name}" collides with an existing feature.')
            return
        c = schema.get(name, {})
        nodes[name] = {
            "name": name,
            "origin": origin,
            "producer": producer or name,
            "stage": stage,
            "depends_on": list(dict.fromkeys(deps)),
            "requires_fit": fitted,
            "semantic_type": c.get("effective_semantic_type")
            or c.get("semantic_override")
            or c.get("inferred_semantic_type", semantic),
            "physical_dtype": c.get("physical_dtype"),
            "included": bool(ir.get("features", {}).get(name, {}).get("included")),
            "predictor_eligible": name != target,
            "inference_required": False,
        }

    for c in columns:
        if c.get("inference_version") not in {
            "temporal-v1",
            "derived-v1",
            "imputation-v1",
            "feature-engineering-v1",
            "outlier-treatment-v1",
        }:
            add(c["name"], "source", 0, [])
    for field, stage in [("temporal", 10), ("derived", 20)]:
        for f in (ir.get(field) or {}).get("features", []):
            add(f["name"], field, stage, references(f["expression"]))
    for name, config in (ir.get("imputation") or {}).get("columns", {}).items():
        deps = [
            name,
            *[
                value
                for rule in config["rules"]
                for value in [*rule.get("group_by", []), *references(rule.get("condition"))]
            ],
        ]
        operations.append((f"imputation:{name}", 20, deps))
        if config.get("indicator"):
            add(config["indicator"], "imputation_indicator", 30, [name], True)
    engineering = (ir.get("feature_engineering") or {}).get("features", [])
    fitted = {"yeo_johnson", "box_cox", "quantile", "width", "quantile_bins", "rare"}
    for f in engineering:
        add(
            f["name"],
            "engineered",
            40,
            [f["source"]],
            f["method"] in fitted,
            "categorical"
            if f["method"] in {"rare", "boundaries", "width", "quantile_bins"}
            else "continuous",
        )
    for f in (ir.get("outlier_treatment") or {}).get("features", []):
        add(f["name"], "outlier", 50, [f["source"]], True, "continuous")
        if f.get("indicator"):
            add(f["indicator"], "outlier_indicator", 50, [f["source"]], True, "binary", f["name"])
    for step in (ir.get("cleaning") or {}).get("steps", []):
        selection = step["kind"] in {"filter", "missing_filter", "deduplicate"}
        deps = ([step["column"]] if "column" in step else step.get("columns", [])) + references(
            step.get("condition")
        )
        operations.append((f"cleaning:{step['id']}", 20 if selection else 0, deps))
    for name in (ir.get("feature_selection") or {}).get("features", []):
        operations.append(("feature_selection", 50, [name]))
    for name, limit, deps in operations:
        for dep in deps:
            if dep == target:
                issue("target_leakage", name, f'{name} cannot use supervised target "{dep}".')
            elif dep not in nodes:
                issue("reference_missing", name, f'{name} refers to missing feature "{dep}".')
            elif nodes[dep]["stage"] > limit:
                issue(
                    "stage_dependency",
                    name,
                    f'{name} requires "{dep}" before its production stage.',
                )
    earlier_engineering = set()
    for f in engineering:
        source = nodes.get(f["source"])
        if (
            source
            and source["origin"] == "engineered"
            and (source["requires_fit"] or f["source"] not in earlier_engineering)
        ):
            issue(
                "stage_dependency",
                f["name"],
                "Engineering chaining requires an earlier stateless output; "
                "fitted/forward chains are unsupported.",
            )
        earlier_engineering.add(f["name"])
    visiting, complete = set(), set()

    def ancestors(name):
        if name in visiting:
            issue("dependency_cycle", name, f'Dependency cycle at "{name}".')
            return []
        node = nodes[name]
        if name in complete:
            return node["ancestors"]
        visiting.add(name)
        result = []
        for dep in node["depends_on"]:
            if dep == target:
                issue(
                    "target_leakage",
                    name,
                    f'Feature "{name}" cannot depend on supervised target "{dep}".',
                )
            if dep not in nodes:
                issue(
                    "reference_missing", name, f'Feature "{name}" requires missing input "{dep}".'
                )
                continue
            source = nodes[dep]
            same = source["stage"] == node["stage"]
            if (
                source["stage"] > node["stage"]
                or (same and node["origin"] in {"outlier", "outlier_indicator"})
                or (
                    node["origin"] in {"engineered", "outlier", "outlier_indicator"}
                    and source["origin"] == "imputation_indicator"
                )
            ):
                issue(
                    "stage_dependency",
                    name,
                    f'Feature "{name}" cannot read "{dep}" at this execution stage.',
                )
            result.extend([*ancestors(dep), dep])
        visiting.remove(name)
        node["ancestors"] = list(dict.fromkeys(v for v in result if v != name))
        complete.add(name)
        return node["ancestors"]

    for name in nodes:
        ancestors(name)
    for node in nodes.values():
        node["dependents"] = [
            name for name, other in nodes.items() if node["name"] in other["ancestors"]
        ]
    required = {name for name, node in nodes.items() if node["included"] and name != target}
    # Existing row-wise stages execute their configured outputs, even if an
    # intermediate output is excluded from the estimator.
    required.update(
        name
        for name, node in nodes.items()
        if node["origin"] not in {"source", "imputation_indicator"}
    )
    required.update((ir.get("temporal") or {}).get("sources", {}))
    for name, limit, deps in operations:
        if name.startswith("cleaning:") and limit == 0:
            required.update(deps)
        if name.startswith("imputation:"):
            imputed = name.split(":", 1)[1]
            if imputed in required or any(
                imputed in nodes[n]["ancestors"] for n in required if n in nodes
            ):
                required.update(deps)
    raw = {
        name
        for value in required
        if value in nodes
        for name in [value, *nodes[value]["ancestors"]]
        if nodes[name]["origin"] == "source" and name != target
    }
    raw_inputs = []
    for name, node in nodes.items():
        if name in raw:
            node["inference_required"] = True
            raw_inputs.append(
                {
                    "name": name,
                    "semantic_type": node["semantic_type"],
                    "physical_dtype": node["physical_dtype"],
                    "missing_policy": "existing_preprocessing",
                    "intermediate_only": not node["included"],
                    "cleaning": [
                        s
                        for s in (ir.get("cleaning") or {}).get("steps", [])
                        if s.get("column") == name
                    ],
                }
            )
    for name, _limit, deps in operations:
        if name.startswith("imputation:"):
            feature = name.split(":", 1)[1]
            if feature in nodes:
                nodes[feature]["requires_fit"] = True
                nodes[feature]["effective_stage"] = 30
                nodes[feature]["operation_dependencies"] = list(
                    dict.fromkeys(dep for dep in deps if dep != feature)
                )
    for node in nodes.values():
        node["predictor_eligible"] = node["predictor_eligible"] and node["semantic_type"] in {
            "continuous",
            "categorical",
            "binary",
        }
    return {
        "features": list(nodes.values()),
        "issues": issues,
        "raw_inputs": raw_inputs,
        "extra_columns": "ignored",
        "version": "lineage-v1",
    }


def contract_intent(ir, dataset):
    return {
        "version": "schema-contract-v1",
        "raw_inputs": registry(ir, dataset.columns)["raw_inputs"],
    }
