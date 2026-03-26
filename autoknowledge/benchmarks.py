"""Benchmark runner for frozen and metamorphic regression cases."""

from __future__ import annotations

import json
import shutil
import tempfile
from pathlib import Path
from typing import Any

from .diffing import summarize_canonical_diff, summarize_diff, summarize_semantic_canonical_diff
from .indexer import index_vault
from .ingest import apply_ingestion_plan, ingest_conversation, ingest_file
from .integrity import validate_index
from .metrics import compute_metrics
from .retrieval_qa import run_question_set


def _make_workspace(*, prefix: str, keep_workdirs: bool) -> tuple[Path, Any]:
    if keep_workdirs:
        root = Path(tempfile.mkdtemp(prefix=prefix))

        def _cleanup() -> None:
            return None

        return root, _cleanup
    workspace = tempfile.TemporaryDirectory(prefix=prefix)
    return Path(workspace.name), workspace.cleanup


def run_benchmark_manifest(
    manifest_path: Path,
    *,
    profile_name: str | None = None,
    vault_profile_name: str | None = None,
    model_override: str | None = None,
    config_root: Path | None = None,
    keep_workdirs: bool = False,
) -> dict[str, Any]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest_dir = manifest_path.parent
    cases = manifest.get("cases", [])

    results = [
        _run_benchmark_case(
            case=case,
            manifest_dir=manifest_dir,
            profile_name=profile_name,
            vault_profile_name=vault_profile_name,
            model_override=model_override,
            config_root=config_root,
            keep_workdirs=keep_workdirs,
        )
        for case in cases
    ]
    passed_count = sum(1 for item in results if item["passed"])
    failed_count = len(results) - passed_count
    return {
        "suite_name": manifest.get("suite_name", manifest_path.stem),
        "manifest_path": str(manifest_path),
        "case_count": len(results),
        "passed_count": passed_count,
        "failed_count": failed_count,
        "all_passed": failed_count == 0,
        "cases": results,
    }


def _run_benchmark_case(
    *,
    case: dict[str, Any],
    manifest_dir: Path,
    profile_name: str | None,
    vault_profile_name: str | None,
    model_override: str | None,
    config_root: Path | None,
    keep_workdirs: bool,
) -> dict[str, Any]:
    case_type = str(case.get("case_type", "frozen"))
    if case_type == "metamorphic":
        return _run_metamorphic_case(
            case=case,
            manifest_dir=manifest_dir,
            profile_name=profile_name,
            vault_profile_name=vault_profile_name,
            model_override=model_override,
            config_root=config_root,
            keep_workdirs=keep_workdirs,
        )
    if case_type == "retrieval_qa":
        return _run_retrieval_qa_case(
            case=case,
            manifest_dir=manifest_dir,
            profile_name=profile_name,
            vault_profile_name=vault_profile_name,
            model_override=model_override,
            config_root=config_root,
            keep_workdirs=keep_workdirs,
        )
    return _run_single_benchmark_case(
        case=case,
        manifest_dir=manifest_dir,
        profile_name=profile_name,
        vault_profile_name=vault_profile_name,
        model_override=model_override,
        config_root=config_root,
        keep_workdirs=keep_workdirs,
    )


def _run_single_benchmark_case(
    *,
    case: dict[str, Any],
    manifest_dir: Path,
    profile_name: str | None,
    vault_profile_name: str | None,
    model_override: str | None,
    config_root: Path | None,
    keep_workdirs: bool,
) -> dict[str, Any]:
    case_id = str(case.get("id", "unknown_case"))
    input_kind = str(case.get("input_kind", "file"))
    expectations = dict(case.get("expect", {}))
    effective_profile = profile_name or case.get("profile")
    effective_vault_profile = vault_profile_name or case.get("vault_profile")
    effective_model = model_override or case.get("model")
    input_path = _resolve_case_input_path(case=case, manifest_dir=manifest_dir)

    workspace_root, cleanup_workspace = _make_workspace(
        prefix=f"autoknowledge_benchmark_{case_id}_",
        keep_workdirs=keep_workdirs,
    )
    vault_root = workspace_root / "vault"
    actual: dict[str, Any] = {}
    failures: list[str] = []

    try:
        try:
            _prepare_case_vault(vault_root=vault_root, case=case, manifest_dir=manifest_dir)
            plan = _build_case_plan(
                input_kind=input_kind,
                vault_root=vault_root,
                input_path=input_path,
                profile_name=effective_profile,
                vault_profile_name=effective_vault_profile,
                model_override=effective_model,
                config_root=config_root,
                case=case,
            )
            apply_result = apply_ingestion_plan(
                vault_root,
                plan,
                vault_profile_name=effective_vault_profile,
                config_root=config_root,
                backup_dir=workspace_root / "backups",
            )
            index = index_vault(vault_root, vault_profile_name=effective_vault_profile, config_root=config_root)
            integrity = validate_index(index, vault_profile_name=effective_vault_profile, config_root=config_root)
            metrics = compute_metrics(index, integrity)
            actual = {
                "plan_stats": plan.stats,
                "apply": apply_result,
                "operation_paths": [item.path for item in plan.operations],
                "create_paths": [item.path for item in plan.operations if item.action == "create"],
                "update_paths": [item.path for item in plan.operations if item.action == "update"],
                "noop_paths": [item.path for item in plan.operations if item.action == "noop"],
                "note_paths": sorted(index.get("by_path", {})),
                "note_texts": _collect_expected_note_texts(vault_root=vault_root, expectations=expectations),
                "integrity": integrity,
                "metrics": metrics,
            }

            if expectations.get("reingest_noop"):
                before_reingest_index = index_vault(vault_root)
                reingest_plan = _build_case_plan(
                    input_kind=input_kind,
                    vault_root=vault_root,
                    input_path=input_path,
                    profile_name=effective_profile,
                    vault_profile_name=effective_vault_profile,
                    model_override=effective_model,
                    config_root=config_root,
                    case=case,
                )
                reingest_apply = apply_ingestion_plan(
                    vault_root,
                    reingest_plan,
                    vault_profile_name=effective_vault_profile,
                    config_root=config_root,
                    backup_dir=workspace_root / "backups",
                )
                after_reingest_index = index_vault(vault_root, vault_profile_name=effective_vault_profile, config_root=config_root)
                actual["reingest_stats"] = reingest_plan.stats
                actual["reingest_apply"] = reingest_apply
                actual["reingest_operations"] = {
                    "create_paths": [item.path for item in reingest_plan.operations if item.action == "create"],
                    "update_paths": [item.path for item in reingest_plan.operations if item.action == "update"],
                    "noop_paths": [item.path for item in reingest_plan.operations if item.action == "noop"],
                }
                actual["reingest_diff"] = summarize_diff(before_reingest_index, after_reingest_index)
                actual["reingest_canonical_diff"] = summarize_canonical_diff(before_reingest_index, after_reingest_index)
                actual["reingest_semantic_canonical_diff"] = summarize_semantic_canonical_diff(
                    before_reingest_index,
                    after_reingest_index,
                )
        except Exception as exc:  # noqa: BLE001
            actual = {"error": str(exc)}

        failures = _evaluate_case(expectations=expectations, actual=actual)
        result = {
            "id": case_id,
            "input_kind": input_kind,
            "input_path": str(input_path),
            "profile": effective_profile,
            "vault_profile": effective_vault_profile,
            "model": effective_model,
            "passed": not failures,
            "failures": failures,
            "actual": actual,
        }
        if keep_workdirs:
            result["workspace"] = str(workspace_root)
        return result
    finally:
        cleanup_workspace()


def _run_metamorphic_case(
    *,
    case: dict[str, Any],
    manifest_dir: Path,
    profile_name: str | None,
    vault_profile_name: str | None,
    model_override: str | None,
    config_root: Path | None,
    keep_workdirs: bool,
) -> dict[str, Any]:
    case_id = str(case.get("id", "unknown_metamorphic_case"))
    root, cleanup_workspace = _make_workspace(
        prefix=f"autoknowledge_metamorphic_{case_id}_",
        keep_workdirs=keep_workdirs,
    )
    variant_a = dict(case.get("baseline", {}))
    variant_b = dict(case.get("transformed", {}))
    expectations = dict(case.get("expect", {}))

    actual: dict[str, Any] = {}
    failures: list[str] = []

    try:
        try:
            baseline_result = _run_variant(
                case=case,
                variant=variant_a,
                variant_name="baseline",
                variant_root=root / "baseline",
                manifest_dir=manifest_dir,
                profile_name=profile_name,
                vault_profile_name=vault_profile_name,
                model_override=model_override,
                config_root=config_root,
            )
            transformed_result = _run_variant(
                case=case,
                variant=variant_b,
                variant_name="transformed",
                variant_root=root / "transformed",
                manifest_dir=manifest_dir,
                profile_name=profile_name,
                vault_profile_name=vault_profile_name,
                model_override=model_override,
                config_root=config_root,
            )
            comparison = {
                "canonical_diff": summarize_canonical_diff(
                    baseline_result["index"],
                    transformed_result["index"],
                ),
                "semantic_canonical_diff": summarize_semantic_canonical_diff(
                    baseline_result["index"],
                    transformed_result["index"],
                ),
                "metric_deltas": _metric_deltas(
                    baseline_result["metrics"],
                    transformed_result["metrics"],
                ),
                "window_count_delta": abs(
                    int(baseline_result["plan_stats"].get("window_count", 0))
                    - int(transformed_result["plan_stats"].get("window_count", 0))
                ),
            }
            actual = {
                "baseline": _public_variant_result(baseline_result),
                "transformed": _public_variant_result(transformed_result),
                "comparison": comparison,
            }
        except Exception as exc:  # noqa: BLE001
            actual = {"error": str(exc)}

        failures = _evaluate_metamorphic_case(expectations=expectations, actual=actual)
        result = {
            "id": case_id,
            "case_type": "metamorphic",
            "passed": not failures,
            "failures": failures,
            "actual": actual,
        }
        if keep_workdirs:
            result["workspace"] = str(root)
        return result
    finally:
        cleanup_workspace()


def _run_retrieval_qa_case(
    *,
    case: dict[str, Any],
    manifest_dir: Path,
    profile_name: str | None,
    vault_profile_name: str | None,
    model_override: str | None,
    config_root: Path | None,
    keep_workdirs: bool,
) -> dict[str, Any]:
    case_id = str(case.get("id", "unknown_retrieval_case"))
    input_kind = str(case.get("input_kind", "file"))
    expectations = dict(case.get("expect", {}))
    effective_profile = profile_name or case.get("profile")
    effective_vault_profile = vault_profile_name or case.get("vault_profile")
    effective_model = model_override or case.get("model")
    input_path = _resolve_case_input_path(case=case, manifest_dir=manifest_dir)

    workspace_root, cleanup_workspace = _make_workspace(
        prefix=f"autoknowledge_retrieval_{case_id}_",
        keep_workdirs=keep_workdirs,
    )
    vault_root = workspace_root / "vault"
    actual: dict[str, Any] = {}
    failures: list[str] = []

    try:
        try:
            _prepare_case_vault(vault_root=vault_root, case=case, manifest_dir=manifest_dir)
            plan = _build_case_plan(
                input_kind=input_kind,
                vault_root=vault_root,
                input_path=input_path,
                profile_name=effective_profile,
                vault_profile_name=effective_vault_profile,
                model_override=effective_model,
                config_root=config_root,
                case=case,
            )
            apply_result = apply_ingestion_plan(
                vault_root,
                plan,
                vault_profile_name=effective_vault_profile,
                config_root=config_root,
                backup_dir=workspace_root / "backups",
            )
            index = index_vault(vault_root, vault_profile_name=effective_vault_profile, config_root=config_root)
            integrity = validate_index(index, vault_profile_name=effective_vault_profile, config_root=config_root)
            metrics = compute_metrics(index, integrity)
            qa = run_question_set(
                index,
                list(case.get("questions", [])),
                default_top_k=int(case.get("top_k", 5)),
                default_scope=str(case.get("scope", "canonical")),
            )
            actual = {
                "plan_stats": plan.stats,
                "apply": apply_result,
                "operation_paths": [item.path for item in plan.operations],
                "create_paths": [item.path for item in plan.operations if item.action == "create"],
                "update_paths": [item.path for item in plan.operations if item.action == "update"],
                "noop_paths": [item.path for item in plan.operations if item.action == "noop"],
                "note_paths": sorted(index.get("by_path", {})),
                "note_texts": _collect_expected_note_texts(vault_root=vault_root, expectations=expectations),
                "integrity": integrity,
                "metrics": metrics,
                "qa": qa,
            }
        except Exception as exc:  # noqa: BLE001
            actual = {"error": str(exc)}

        failures = _evaluate_case(expectations=expectations, actual=actual)
        failures.extend(_evaluate_retrieval_case(expectations=expectations, actual=actual))
        result = {
            "id": case_id,
            "case_type": "retrieval_qa",
            "input_kind": input_kind,
            "input_path": str(input_path),
            "profile": effective_profile,
            "vault_profile": effective_vault_profile,
            "model": effective_model,
            "passed": not failures,
            "failures": failures,
            "actual": actual,
        }
        if keep_workdirs:
            result["workspace"] = str(workspace_root)
        return result
    finally:
        cleanup_workspace()


def _run_variant(
    *,
    case: dict[str, Any],
    variant: dict[str, Any],
    variant_name: str,
    variant_root: Path,
    manifest_dir: Path,
    profile_name: str | None,
    vault_profile_name: str | None,
    model_override: str | None,
    config_root: Path | None,
) -> dict[str, Any]:
    input_kind = str(variant.get("input_kind") or case.get("input_kind", "file"))
    input_ref = variant.get("input_path") or case.get("input_path")
    input_path = (manifest_dir / str(input_ref or "")).resolve()
    effective_profile = profile_name or variant.get("profile") or case.get("profile")
    effective_vault_profile = vault_profile_name or variant.get("vault_profile") or case.get("vault_profile")
    effective_model = model_override or variant.get("model") or case.get("model")
    transformed_input_path = _prepare_variant_input(
        input_kind=input_kind,
        input_path=input_path,
        variant_root=variant_root,
        transform=variant.get("transform"),
    )
    vault_root = variant_root / "vault"
    plan = _build_case_plan(
        input_kind=input_kind,
        vault_root=vault_root,
        input_path=transformed_input_path,
        profile_name=effective_profile,
        vault_profile_name=effective_vault_profile,
        model_override=effective_model,
        config_root=config_root,
        case={**case, **variant},
    )
    apply_result = apply_ingestion_plan(
        vault_root,
        plan,
        vault_profile_name=effective_vault_profile,
        config_root=config_root,
        backup_dir=variant_root / "backups",
    )
    index = index_vault(vault_root, vault_profile_name=effective_vault_profile, config_root=config_root)
    integrity = validate_index(index, vault_profile_name=effective_vault_profile, config_root=config_root)
    metrics = compute_metrics(index, integrity)
    return {
        "variant_name": variant_name,
        "input_kind": input_kind,
        "input_path": str(transformed_input_path),
        "profile": effective_profile,
        "vault_profile": effective_vault_profile,
        "model": effective_model,
        "apply": apply_result,
        "index": index,
        "integrity": integrity,
        "metrics": metrics,
        "plan_stats": plan.stats,
    }


def _public_variant_result(result: dict[str, Any]) -> dict[str, Any]:
    return {
        "variant_name": result["variant_name"],
        "input_kind": result["input_kind"],
        "input_path": result["input_path"],
        "profile": result["profile"],
        "vault_profile": result.get("vault_profile"),
        "model": result["model"],
        "apply": result["apply"],
        "integrity": result["integrity"],
        "metrics": result["metrics"],
        "plan_stats": result["plan_stats"],
    }


def _build_case_plan(
    *,
    input_kind: str,
    vault_root: Path,
    input_path: Path,
    profile_name: str | None,
    vault_profile_name: str | None,
    model_override: str | None,
    config_root: Path | None,
    case: dict[str, Any],
):
    if input_kind == "file":
        return ingest_file(
            vault_root=vault_root,
            input_path=input_path,
            origin=case.get("origin"),
            title=case.get("title"),
            profile_name=profile_name,
            vault_profile_name=vault_profile_name,
            model_override=model_override,
            config_root=config_root,
        )
    if input_kind == "conversation":
        return ingest_conversation(
            vault_root=vault_root,
            input_path=input_path,
            origin=case.get("origin"),
            title=case.get("title"),
            channel=case.get("channel"),
            profile_name=profile_name,
            vault_profile_name=vault_profile_name,
            model_override=model_override,
            config_root=config_root,
        )
    raise ValueError(f"Unsupported benchmark input kind: {input_kind}")


def _resolve_case_input_path(*, case: dict[str, Any], manifest_dir: Path) -> Path:
    return (manifest_dir / str(case.get("input_path", ""))).resolve()


def _prepare_case_vault(*, vault_root: Path, case: dict[str, Any], manifest_dir: Path) -> None:
    seed_ref = str(case.get("vault_seed_dir", "")).strip()
    if not seed_ref:
        return
    seed_root = (manifest_dir / seed_ref).resolve()
    if not seed_root.exists():
        raise ValueError(f"Benchmark vault seed dir not found: {seed_root}")
    shutil.copytree(seed_root, vault_root, dirs_exist_ok=True)


def _prepare_variant_input(
    *,
    input_kind: str,
    input_path: Path,
    variant_root: Path,
    transform: dict[str, Any] | None,
) -> Path:
    if not transform:
        return input_path
    if input_kind not in {"file", "conversation"}:
        raise ValueError(f"Unsupported transformed input kind: {input_kind}")

    text = input_path.read_text(encoding="utf-8")
    transformed_text = _apply_text_transform(text=text, transform=transform)
    target = variant_root / "inputs" / input_path.name
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(transformed_text, encoding="utf-8")
    return target


def _apply_text_transform(*, text: str, transform: dict[str, Any]) -> str:
    transform_type = str(transform.get("type", "")).strip()
    payload = str(transform.get("text", ""))
    if transform_type == "append_boilerplate":
        suffix = ("\n\n" if text and not text.endswith("\n") else "\n") + payload.strip() + "\n"
        return text + suffix
    if transform_type == "prepend_boilerplate":
        prefix = payload.strip() + ("\n\n" if text else "\n")
        return prefix + text
    raise ValueError(f"Unsupported transform type: {transform_type}")


def _evaluate_case(*, expectations: dict[str, Any], actual: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    expected_outcome = str(expectations.get("outcome", "success"))
    error = str(actual.get("error", "")).strip()

    if expected_outcome == "error":
        if not error:
            failures.append("expected error outcome but the case succeeded")
            return failures
        required_fragment = str(expectations.get("error_contains", "")).strip()
        if required_fragment and required_fragment not in error:
            failures.append(f"expected error containing {required_fragment!r}, got {error!r}")
        return failures

    if error:
        failures.append(f"unexpected error: {error}")
        return failures

    metrics = dict(actual.get("metrics", {}))
    integrity = dict(actual.get("integrity", {}))
    plan_stats = dict(actual.get("plan_stats", {}))
    reingest_stats = dict(actual.get("reingest_stats", {}))

    _check_min(failures, metrics, "citation_coverage", expectations.get("citation_coverage_min"))
    _check_min(failures, metrics, "canonical_note_count", expectations.get("canonical_note_count_min"))
    _check_min(failures, metrics, "claim_count", expectations.get("claim_count_min"))
    _check_min(failures, metrics, "grounded_note_rate", expectations.get("grounded_note_rate_min"))
    _check_min(failures, metrics, "canonical_link_density", expectations.get("canonical_link_density_min"))
    _check_max(failures, metrics, "unsupported_claim_rate", expectations.get("unsupported_claim_rate_max"))
    _check_max(failures, metrics, "duplicate_note_rate", expectations.get("duplicate_note_rate_max"))
    _check_max(failures, metrics, "duplicate_cluster_count", expectations.get("duplicate_cluster_count_max"))
    _check_max(failures, metrics, "broken_link_count", expectations.get("broken_link_count_max"))
    _check_max(failures, metrics, "orphan_note_rate", expectations.get("orphan_note_rate_max"))
    _check_max(failures, metrics, "isolated_note_rate", expectations.get("isolated_note_rate_max"))
    _check_max(
        failures,
        metrics,
        "hard_constraint_issue_count",
        expectations.get("hard_constraint_issue_count_max"),
    )
    _check_max(failures, integrity, "issue_count", expectations.get("integrity_issue_count_max"))
    _check_bool(failures, plan_stats, "windowed", expectations.get("windowed"))
    _check_min(failures, plan_stats, "window_count", expectations.get("window_count_min"))
    _check_contains_all(failures, actual.get("note_paths", []), expectations.get("expected_note_paths_all"), "note_paths")
    _check_contains_any(failures, actual.get("note_paths", []), expectations.get("expected_note_paths_any"), "note_paths")
    _check_contains_all(
        failures,
        actual.get("create_paths", []),
        expectations.get("expected_create_paths_all"),
        "create_paths",
    )
    _check_contains_any(
        failures,
        actual.get("create_paths", []),
        expectations.get("expected_create_paths_any"),
        "create_paths",
    )
    _check_contains_all(
        failures,
        actual.get("update_paths", []),
        expectations.get("expected_update_paths_all"),
        "update_paths",
    )
    _check_contains_any(
        failures,
        actual.get("update_paths", []),
        expectations.get("expected_update_paths_any"),
        "update_paths",
    )
    _check_contains_none(
        failures,
        actual.get("note_paths", []),
        expectations.get("forbidden_note_paths_all"),
        "note_paths",
    )
    _check_contains_none(
        failures,
        actual.get("create_paths", []),
        expectations.get("forbidden_create_paths_all"),
        "create_paths",
    )
    _check_note_substrings(
        failures,
        actual.get("note_texts", {}),
        expectations.get("expected_note_substrings_all"),
        expect_present=True,
    )
    _check_note_substrings(
        failures,
        actual.get("note_texts", {}),
        expectations.get("forbidden_note_substrings_all"),
        expect_present=False,
    )

    if expectations.get("reingest_noop"):
        if not reingest_stats:
            failures.append("expected reingest stats but none were recorded")
        else:
            if int(reingest_stats.get("create_count", -1)) != 0:
                failures.append(f"expected reingest create_count=0, got {reingest_stats.get('create_count')}")
            if int(reingest_stats.get("update_count", -1)) != 0:
                failures.append(f"expected reingest update_count=0, got {reingest_stats.get('update_count')}")
            if int(reingest_stats.get("noop_count", -1)) != int(reingest_stats.get("operation_count", -2)):
                failures.append("expected reingest noop_count to equal operation_count")

    return failures


def _evaluate_metamorphic_case(*, expectations: dict[str, Any], actual: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    error = str(actual.get("error", "")).strip()
    if error:
        failures.append(f"unexpected error: {error}")
        return failures

    baseline = dict(actual.get("baseline", {}))
    transformed = dict(actual.get("transformed", {}))
    comparison = dict(actual.get("comparison", {}))
    canonical_diff = dict(comparison.get("semantic_canonical_diff", {}))
    metric_deltas = dict(comparison.get("metric_deltas", {}))

    _check_max(failures, baseline.get("integrity", {}), "issue_count", expectations.get("baseline_integrity_issue_count_max"))
    _check_max(
        failures,
        transformed.get("integrity", {}),
        "issue_count",
        expectations.get("transformed_integrity_issue_count_max"),
    )
    _check_max(failures, canonical_diff, "graph_churn", expectations.get("canonical_graph_churn_max"))
    _check_max(failures, canonical_diff, "graph_churn_rate", expectations.get("canonical_graph_churn_rate_max"))
    _check_max(failures, canonical_diff, "added_count", expectations.get("canonical_added_count_max"))
    _check_max(failures, canonical_diff, "removed_count", expectations.get("canonical_removed_count_max"))
    _check_max(failures, canonical_diff, "changed_count", expectations.get("canonical_changed_count_max"))
    _check_max_abs(failures, metric_deltas, "canonical_note_count", expectations.get("canonical_note_count_delta_max"))
    _check_max_abs(failures, metric_deltas, "claim_count", expectations.get("claim_count_delta_max"))
    _check_max_abs(failures, metric_deltas, "duplicate_note_rate", expectations.get("duplicate_note_rate_delta_max"))
    _check_max_abs(failures, metric_deltas, "citation_coverage", expectations.get("citation_coverage_delta_max"))
    _check_max_abs(failures, comparison, "window_count_delta", expectations.get("window_count_delta_max"))
    return failures


def _evaluate_retrieval_case(*, expectations: dict[str, Any], actual: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    error = str(actual.get("error", "")).strip()
    if error:
        failures.append(f"unexpected error: {error}")
        return failures

    qa = dict(actual.get("qa", {}))
    _check_min(failures, qa, "question_count", expectations.get("qa_question_count_min"))
    _check_min(failures, qa, "accuracy", expectations.get("qa_accuracy_min"))
    _check_min(failures, qa, "note_hit_rate", expectations.get("qa_note_hit_rate_min"))
    _check_min(failures, qa, "citation_hit_rate", expectations.get("qa_citation_hit_rate_min"))

    failed_questions = [item["id"] for item in qa.get("questions", []) if not item.get("passed")]
    if failed_questions:
        failures.append(f"retrieval QA question failures: {', '.join(failed_questions)}")
    return failures


def _metric_deltas(baseline: dict[str, Any], transformed: dict[str, Any]) -> dict[str, Any]:
    keys = sorted(set(baseline) | set(transformed))
    deltas: dict[str, Any] = {}
    for key in keys:
        left = baseline.get(key)
        right = transformed.get(key)
        if isinstance(left, (int, float)) and isinstance(right, (int, float)):
            deltas[key] = right - left
    return deltas


def _check_min(failures: list[str], values: dict[str, Any], key: str, expected: Any) -> None:
    if expected is None:
        return
    actual = values.get(key)
    if actual is None or float(actual) < float(expected):
        failures.append(f"expected {key} >= {expected}, got {actual}")


def _check_max(failures: list[str], values: dict[str, Any], key: str, expected: Any) -> None:
    if expected is None:
        return
    actual = values.get(key)
    if actual is None or float(actual) > float(expected):
        failures.append(f"expected {key} <= {expected}, got {actual}")


def _check_bool(failures: list[str], values: dict[str, Any], key: str, expected: Any) -> None:
    if expected is None:
        return
    actual = values.get(key)
    if bool(actual) is not bool(expected):
        failures.append(f"expected {key} == {bool(expected)}, got {actual}")


def _check_max_abs(failures: list[str], values: dict[str, Any], key: str, expected: Any) -> None:
    if expected is None:
        return
    actual = values.get(key)
    if actual is None or abs(float(actual)) > float(expected):
        failures.append(f"expected abs({key}) <= {expected}, got {actual}")


def _check_contains_all(failures: list[str], values: Any, expected: Any, label: str) -> None:
    if expected is None:
        return
    actual_values = {str(item) for item in list(values or [])}
    missing = [str(item) for item in list(expected) if str(item) not in actual_values]
    if missing:
        failures.append(f"expected {label} to contain all of {missing}, got {sorted(actual_values)}")


def _check_contains_any(failures: list[str], values: Any, expected: Any, label: str) -> None:
    if expected is None:
        return
    actual_values = {str(item) for item in list(values or [])}
    wanted = [str(item) for item in list(expected)]
    if not any(item in actual_values for item in wanted):
        failures.append(f"expected {label} to contain any of {wanted}, got {sorted(actual_values)}")


def _check_contains_none(failures: list[str], values: Any, expected: Any, label: str) -> None:
    if expected is None:
        return
    actual_values = {str(item) for item in list(values or [])}
    present = [str(item) for item in list(expected) if str(item) in actual_values]
    if present:
        failures.append(f"expected {label} to contain none of {present}, got {sorted(actual_values)}")


def _check_note_substrings(
    failures: list[str],
    note_texts: Any,
    expected: Any,
    *,
    expect_present: bool,
) -> None:
    if expected is None:
        return
    texts = {str(path): str(text) for path, text in dict(note_texts or {}).items()}
    for path, snippets in dict(expected).items():
        text = texts.get(str(path))
        if text is None:
            failures.append(f"expected note text for {path}, but it was not collected")
            continue
        for snippet in list(snippets or []):
            present = str(snippet) in text
            if expect_present and not present:
                failures.append(f"expected note {path} to contain {snippet!r}")
            if not expect_present and present:
                failures.append(f"expected note {path} to not contain {snippet!r}")


def _collect_expected_note_texts(*, vault_root: Path, expectations: dict[str, Any]) -> dict[str, str]:
    paths: set[str] = set()
    for key in ("expected_note_substrings_all", "forbidden_note_substrings_all"):
        for path in dict(expectations.get(key, {})).keys():
            paths.add(str(path))
    note_texts: dict[str, str] = {}
    for rel_path in sorted(paths):
        note_path = vault_root / rel_path
        if note_path.exists():
            note_texts[rel_path] = note_path.read_text(encoding="utf-8")
    return note_texts
