"""Bounded self-update runner for skill-pack changes."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .ledger import append_record
from .providers import propose_skill_change_with_provider
from .repo_context import read_repo_text, repo_root
from .runtime_config import resolve_named_profile

DEFAULT_POLICY_PATH = Path("config/self_update.json")


def load_self_update_policy(path: Path | None = None) -> dict[str, Any]:
    policy_path = path or DEFAULT_POLICY_PATH
    return json.loads(policy_path.read_text(encoding="utf-8"))


def run_self_update(
    *,
    policy_path: Path | None = None,
    config_root: Path | None = None,
    proposal_profile_name: str | None = None,
    proposal_model_override: str | None = None,
    benchmark_profile_name: str | None = None,
    benchmark_model_override: str | None = None,
    apply_accepted: bool = False,
    keep_workdirs: bool = False,
) -> dict[str, Any]:
    live_repo_root = repo_root()
    effective_policy_path = _resolve_path(live_repo_root, policy_path or DEFAULT_POLICY_PATH)
    effective_config_root = _resolve_path(live_repo_root, config_root or Path("config"))
    policy = load_self_update_policy(effective_policy_path)
    run_id = _run_id()
    artifacts_root = _resolve_path(live_repo_root, Path(policy.get("artifacts_root", "artifacts/self_update")))
    run_dir = artifacts_root / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    effective_proposal_profile = proposal_profile_name or policy.get("default_profiles", {}).get("proposal")
    effective_benchmark_profile = benchmark_profile_name or policy.get("default_profiles", {}).get("benchmark")
    if not effective_benchmark_profile:
        raise ValueError("No benchmark profile configured for self-update")

    proposal_profile = None
    if effective_proposal_profile:
        proposal_profile = resolve_named_profile(
            profile_name=effective_proposal_profile,
            model_override=proposal_model_override,
            config_root=effective_config_root,
        )
    benchmark_profile = resolve_named_profile(
        profile_name=effective_benchmark_profile,
        model_override=benchmark_model_override,
        config_root=effective_config_root,
    )

    benchmark_warning = None
    if benchmark_profile.get("backend") == "deterministic":
        benchmark_warning = (
            "benchmark backend is deterministic; prompt-only skill edits are unlikely to change outcomes"
        )

    summary_record = {
        "run_id": run_id,
        "policy_path": str(effective_policy_path),
        "proposal_profile": proposal_profile["name"] if proposal_profile else None,
        "proposal_model": proposal_profile.get("model") if proposal_profile else None,
        "benchmark_profile": benchmark_profile["name"],
        "benchmark_model": benchmark_profile.get("model"),
        "benchmark_backend": benchmark_profile.get("backend"),
        "benchmark_warning": benchmark_warning,
    }
    _write_json(run_dir / "run_context.json", summary_record)

    try:
        baseline = _run_benchmark_stack(
            repo=live_repo_root,
            manifests=[Path(item) for item in policy.get("benchmark_manifests", [])],
            profile_name=benchmark_profile["name"],
            model_override=benchmark_profile.get("model"),
            keep_workdirs=keep_workdirs,
            output_dir=run_dir / "baseline",
        )
        failure_clusters = cluster_failures(report=baseline, policy=policy)
        proposal = _generate_skill_change_proposal(
            policy=policy,
            failure_clusters=failure_clusters,
            baseline=baseline,
            proposal_profile=proposal_profile,
            live_repo_root=live_repo_root,
        )
        _validate_target_path(proposal["target_path"], policy.get("allowed_skill_targets", []))
        _write_json(run_dir / "proposal.json", proposal)

        candidate_workspace = tempfile.TemporaryDirectory(prefix=f"autoknowledge_self_update_{run_id}_")
        candidate_repo_root = Path(candidate_workspace.name) / "repo"
        shutil.copytree(
            live_repo_root,
            candidate_repo_root,
            ignore=shutil.ignore_patterns(".git", "__pycache__", ".pytest_cache", "artifacts", "state", "vault"),
        )
        _apply_candidate_skill_change(candidate_repo_root=candidate_repo_root, proposal=proposal)

        candidate = _run_benchmark_stack(
            repo=candidate_repo_root,
            manifests=[Path(item) for item in policy.get("benchmark_manifests", [])],
            profile_name=benchmark_profile["name"],
            model_override=benchmark_profile.get("model"),
            keep_workdirs=keep_workdirs,
            output_dir=run_dir / "candidate",
        )
        decision = compare_reports(
            baseline=baseline,
            candidate=candidate,
            policy=policy,
            failure_clusters=failure_clusters,
        )

        applied_path = None
        if decision["accepted"] and apply_accepted:
            applied_path = _copy_accepted_skill_change(
                live_repo_root=live_repo_root,
                candidate_repo_root=candidate_repo_root,
                target_path=proposal["target_path"],
            )
            decision["applied"] = True
            decision["applied_path"] = applied_path
        else:
            decision["applied"] = False
            decision["applied_path"] = None

        result = {
            **summary_record,
            "status": "accepted" if decision["accepted"] else "rejected",
            "apply_accepted": apply_accepted,
            "artifacts_dir": str(run_dir),
            "proposal": proposal,
            "baseline": baseline,
            "failure_clusters": failure_clusters,
            "candidate": candidate,
            "decision": decision,
        }
        _write_json(run_dir / "result.json", result)
        append_record(
            _resolve_path(live_repo_root, Path(policy.get("ledger_path", "state/ledger.jsonl"))),
            kind="self-update",
            status=result["status"],
            summary=_ledger_summary(result),
            details_path=str(run_dir / "result.json"),
            metrics_path=str(run_dir / "candidate" / "summary.json"),
        )
        if not keep_workdirs:
            candidate_workspace.cleanup()
        else:
            result["candidate_workspace"] = str(candidate_repo_root)
        return result
    except Exception as exc:  # noqa: BLE001
        error_result = {
            **summary_record,
            "status": "failed",
            "artifacts_dir": str(run_dir),
            "error": str(exc),
        }
        _write_json(run_dir / "result.json", error_result)
        append_record(
            _resolve_path(live_repo_root, Path(policy.get("ledger_path", "state/ledger.jsonl"))),
            kind="self-update",
            status="failed",
            summary=f"self-update failed: {exc}",
            details_path=str(run_dir / "result.json"),
            metrics_path=None,
        )
        raise


def cluster_failures(*, report: dict[str, Any], policy: dict[str, Any]) -> list[dict[str, Any]]:
    clusters: dict[str, dict[str, Any]] = {}
    for suite in report.get("suites", []):
        suite_name = str(suite.get("suite_name", "unknown_suite"))
        for case in suite.get("cases", []):
            for failure in case.get("failures", []):
                code, summary, priority = _classify_failure_message(str(failure))
                cluster = clusters.setdefault(
                    code,
                    {
                        "code": code,
                        "summary": summary,
                        "priority": priority,
                        "count": 0,
                        "examples": [],
                        "suites": [],
                    },
                )
                cluster["count"] += 1
                if suite_name not in cluster["suites"]:
                    cluster["suites"].append(suite_name)
                if len(cluster["examples"]) < 3:
                    cluster["examples"].append(
                        {
                            "suite": suite_name,
                            "case_id": case.get("id"),
                            "failure": failure,
                        }
                    )

    aggregate = dict(report.get("aggregate", {}))
    thresholds = dict(policy.get("warning_thresholds", {}))
    _maybe_add_metric_cluster(
        clusters,
        code="high_isolated_note_rate",
        summary="Canonical notes are grounded but remain too isolated.",
        priority=70,
        metric_name="isolated_note_rate",
        metric_value=aggregate.get("isolated_note_rate"),
        threshold=thresholds.get("isolated_note_rate"),
        direction="max",
    )
    _maybe_add_metric_cluster(
        clusters,
        code="low_canonical_link_density",
        summary="Canonical link density is too low.",
        priority=65,
        metric_name="canonical_link_density",
        metric_value=aggregate.get("canonical_link_density"),
        threshold=thresholds.get("canonical_link_density"),
        direction="min",
    )
    _maybe_add_metric_cluster(
        clusters,
        code="high_duplicate_note_rate",
        summary="Duplicate note rate is too high.",
        priority=75,
        metric_name="duplicate_note_rate",
        metric_value=aggregate.get("duplicate_note_rate"),
        threshold=thresholds.get("duplicate_note_rate"),
        direction="max",
    )
    _maybe_add_metric_cluster(
        clusters,
        code="high_duplicate_cluster_count",
        summary="Too many duplicate candidate clusters are present.",
        priority=74,
        metric_name="duplicate_cluster_count",
        metric_value=aggregate.get("duplicate_cluster_count"),
        threshold=thresholds.get("duplicate_cluster_count"),
        direction="max",
    )
    _maybe_add_metric_cluster(
        clusters,
        code="high_graph_churn_rate",
        summary="Metamorphic graph churn is too high.",
        priority=68,
        metric_name="graph_churn_rate",
        metric_value=aggregate.get("graph_churn_rate"),
        threshold=thresholds.get("graph_churn_rate"),
        direction="max",
    )
    _maybe_add_metric_cluster(
        clusters,
        code="low_retrieval_qa_accuracy",
        summary="Retrieval QA accuracy is too low.",
        priority=78,
        metric_name="retrieval_qa_accuracy",
        metric_value=aggregate.get("retrieval_qa_accuracy"),
        threshold=thresholds.get("retrieval_qa_accuracy"),
        direction="min",
    )
    _maybe_add_metric_cluster(
        clusters,
        code="low_retrieval_citation_hit_rate",
        summary="Retrieved answers miss the expected source citations too often.",
        priority=77,
        metric_name="retrieval_qa_citation_hit_rate",
        metric_value=aggregate.get("retrieval_qa_citation_hit_rate"),
        threshold=thresholds.get("citation_hit_rate"),
        direction="min",
    )

    ordered = sorted(
        clusters.values(),
        key=lambda item: (-int(item.get("priority", 0)), -int(item.get("count", 0)), str(item.get("code", ""))),
    )
    return ordered


def compare_reports(
    *,
    baseline: dict[str, Any],
    candidate: dict[str, Any],
    policy: dict[str, Any],
    failure_clusters: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    comparison = dict(policy.get("comparison", {}))
    baseline_metrics = dict(baseline.get("aggregate", {}))
    candidate_metrics = dict(candidate.get("aggregate", {}))
    rejection_reasons: list[str] = []
    improvement_reasons: list[str] = []
    primary_cluster = dict((failure_clusters or [{}])[0]) if failure_clusters else {}

    _reject_if_higher(
        rejection_reasons,
        "failed_case_count",
        baseline_metrics,
        candidate_metrics,
        float(comparison.get("max_failed_case_regression", 0)),
    )
    _reject_if_higher(
        rejection_reasons,
        "hard_constraint_issue_count",
        baseline_metrics,
        candidate_metrics,
        float(comparison.get("max_hard_constraint_issue_regression", 0)),
    )
    _reject_if_higher(
        rejection_reasons,
        "duplicate_note_rate",
        baseline_metrics,
        candidate_metrics,
        float(comparison.get("max_duplicate_note_rate_regression", 0.0)),
    )
    _reject_if_higher(
        rejection_reasons,
        "isolated_note_rate",
        baseline_metrics,
        candidate_metrics,
        float(comparison.get("max_isolated_note_rate_regression", 0.0)),
    )
    _reject_if_higher(
        rejection_reasons,
        "graph_churn_rate",
        baseline_metrics,
        candidate_metrics,
        float(comparison.get("max_graph_churn_rate_regression", 0.0)),
    )
    _reject_if_lower(
        rejection_reasons,
        "retrieval_qa_accuracy",
        baseline_metrics,
        candidate_metrics,
        float(comparison.get("max_retrieval_qa_regression", 0.0)),
    )
    _reject_if_lower(
        rejection_reasons,
        "canonical_link_density",
        baseline_metrics,
        candidate_metrics,
        float(comparison.get("max_canonical_link_density_regression", 0.0)),
    )

    score_delta = float(candidate_metrics.get("score", 0.0)) - float(baseline_metrics.get("score", 0.0))
    min_score_improvement = float(comparison.get("min_score_improvement", 0.0))
    if score_delta >= min_score_improvement:
        improvement_reasons.append(f"score improved by {score_delta:.4f}")

    _note_improvement_if_lower(improvement_reasons, "failed_case_count", baseline_metrics, candidate_metrics)
    _note_improvement_if_lower(improvement_reasons, "hard_constraint_issue_count", baseline_metrics, candidate_metrics)
    _note_improvement_if_lower(improvement_reasons, "duplicate_note_rate", baseline_metrics, candidate_metrics)
    _note_improvement_if_lower(improvement_reasons, "isolated_note_rate", baseline_metrics, candidate_metrics)
    _note_improvement_if_lower(improvement_reasons, "graph_churn_rate", baseline_metrics, candidate_metrics)
    _note_improvement_if_higher(improvement_reasons, "retrieval_qa_accuracy", baseline_metrics, candidate_metrics)
    _note_improvement_if_higher(improvement_reasons, "canonical_link_density", baseline_metrics, candidate_metrics)

    primary_requirement = _primary_cluster_requirement(
        cluster_code=str(primary_cluster.get("code", "")).strip(),
        comparison=comparison,
    )
    primary_improvement_reason = _check_primary_cluster_improvement(
        baseline=baseline_metrics,
        candidate=candidate_metrics,
        cluster_code=str(primary_cluster.get("code", "")).strip(),
        requirement=primary_requirement,
    )
    if primary_requirement and primary_improvement_reason is None:
        rejection_reasons.append(
            f"primary failure cluster {primary_cluster.get('code', 'unknown')} did not improve enough"
        )
    elif primary_improvement_reason:
        improvement_reasons.append(primary_improvement_reason)

    if not rejection_reasons and not improvement_reasons:
        rejection_reasons.append("no measurable improvement")

    accepted = not rejection_reasons and bool(improvement_reasons)
    return {
        "accepted": accepted,
        "primary_cluster": primary_cluster.get("code"),
        "primary_requirement": primary_requirement,
        "baseline_score": baseline_metrics.get("score"),
        "candidate_score": candidate_metrics.get("score"),
        "score_delta": score_delta,
        "rejection_reasons": rejection_reasons,
        "improvement_reasons": improvement_reasons,
    }


def _run_benchmark_stack(
    *,
    repo: Path,
    manifests: list[Path],
    profile_name: str,
    model_override: str | None,
    keep_workdirs: bool,
    output_dir: Path,
) -> dict[str, Any]:
    suites = []
    output_dir.mkdir(parents=True, exist_ok=True)
    for manifest in manifests:
        suite_output = output_dir / f"{manifest.stem}.json"
        suite_result = _run_benchmark_command(
            repo=repo,
            manifest=manifest,
            profile_name=profile_name,
            model_override=model_override,
            keep_workdirs=keep_workdirs,
            output_path=suite_output,
        )
        suites.append(suite_result)

    aggregate = _aggregate_benchmark_results(suites=suites)
    summary = {
        "repo": str(repo),
        "manifests": [str(item) for item in manifests],
        "suites": suites,
        "aggregate": aggregate,
    }
    _write_json(output_dir / "summary.json", summary)
    return summary


def _run_benchmark_command(
    *,
    repo: Path,
    manifest: Path,
    profile_name: str,
    model_override: str | None,
    keep_workdirs: bool,
    output_path: Path,
) -> dict[str, Any]:
    command = [
        sys.executable,
        "main.py",
        "benchmark-run",
        "--manifest",
        str(manifest),
        "--profile",
        profile_name,
        "--config-root",
        "config",
        "--output",
        str(output_path),
    ]
    if model_override:
        command.extend(["--model", model_override])
    if keep_workdirs:
        command.append("--keep-workdirs")

    completed = subprocess.run(
        command,
        cwd=repo,
        check=False,
        capture_output=True,
        text=True,
    )
    stdout = completed.stdout.strip()
    if not stdout:
        stderr = completed.stderr.strip()
        raise RuntimeError(f"benchmark-run produced no JSON output for {manifest}: {stderr or 'empty stdout'}")
    try:
        return json.loads(stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"benchmark-run returned invalid JSON for {manifest}: {stdout[:200]!r}") from exc


def _aggregate_benchmark_results(*, suites: list[dict[str, Any]]) -> dict[str, Any]:
    numeric_samples: dict[str, list[float]] = {}
    qa_samples: dict[str, list[float]] = {}
    failed_case_count = 0
    failed_suite_count = 0
    hard_constraint_issue_count = 0

    for suite in suites:
        if not suite.get("all_passed", False):
            failed_suite_count += 1
        failed_case_count += int(suite.get("failed_count", 0))
        for case in suite.get("cases", []):
            actual = dict(case.get("actual", {}))
            metrics = actual.get("metrics")
            if isinstance(metrics, dict):
                for key in (
                    "citation_coverage",
                    "grounded_note_rate",
                    "duplicate_note_rate",
                    "duplicate_cluster_count",
                    "isolated_note_rate",
                    "canonical_link_density",
                    "unsupported_claim_rate",
                ):
                    _append_numeric_sample(numeric_samples, key, metrics.get(key))
                hard_constraint_issue_count += int(metrics.get("hard_constraint_issue_count", 0) or 0)

            qa = actual.get("qa")
            if isinstance(qa, dict):
                _append_numeric_sample(qa_samples, "retrieval_qa_accuracy", qa.get("accuracy"))
                _append_numeric_sample(qa_samples, "retrieval_qa_note_hit_rate", qa.get("note_hit_rate"))
                _append_numeric_sample(qa_samples, "retrieval_qa_citation_hit_rate", qa.get("citation_hit_rate"))

            comparison = actual.get("comparison")
            if isinstance(comparison, dict):
                semantic_diff = comparison.get("semantic_canonical_diff")
                if isinstance(semantic_diff, dict):
                    _append_numeric_sample(numeric_samples, "graph_churn_rate", semantic_diff.get("graph_churn_rate"))

    aggregate = {
        "suite_count": len(suites),
        "failed_suite_count": failed_suite_count,
        "failed_case_count": failed_case_count,
        "hard_constraint_issue_count": hard_constraint_issue_count,
    }
    for key, values in numeric_samples.items():
        if values:
            aggregate[key] = sum(values) / len(values)
    for key, values in qa_samples.items():
        if values:
            aggregate[key] = sum(values) / len(values)
    aggregate["score"] = _compute_composite_score(aggregate)
    return aggregate


def _generate_skill_change_proposal(
    *,
    policy: dict[str, Any],
    failure_clusters: list[dict[str, Any]],
    baseline: dict[str, Any],
    proposal_profile: dict[str, Any] | None,
    live_repo_root: Path,
) -> dict[str, Any]:
    allowed_targets = list(policy.get("allowed_skill_targets", []))
    if not allowed_targets:
        raise ValueError("No allowed_skill_targets configured for self-update")

    if proposal_profile and proposal_profile.get("backend") != "deterministic":
        proposal = propose_skill_change_with_provider(
            profile=proposal_profile,
            policy=policy,
            baseline_summary=baseline.get("aggregate", {}),
            failure_clusters=failure_clusters,
            allowed_targets=allowed_targets,
        )
        if proposal.get("target_path") and not proposal.get("target_files"):
            proposal["target_files"] = [proposal["target_path"]]
        proposal["proposal_source"] = "provider"
        return proposal

    heuristic = _heuristic_skill_change_proposal(
        failure_clusters=failure_clusters,
        allowed_targets=allowed_targets,
        live_repo_root=live_repo_root,
    )
    heuristic["proposal_source"] = "heuristic"
    return heuristic


def _heuristic_skill_change_proposal(
    *,
    failure_clusters: list[dict[str, Any]],
    allowed_targets: list[str],
    live_repo_root: Path,
) -> dict[str, Any]:
    primary = failure_clusters[0] if failure_clusters else {
        "code": "high_isolated_note_rate",
        "summary": "Canonical notes remain too isolated.",
    }
    target_path = _select_target_path(primary_code=str(primary.get("code", "")), allowed_targets=allowed_targets)
    current_content = read_repo_text(target_path, root=live_repo_root)
    candidate_content = _apply_heuristic_edit(current_content=current_content, primary_code=str(primary.get("code", "")))
    return {
        "target_path": target_path,
        "target_files": [target_path],
        "rationale": f"Address primary failure cluster: {primary.get('summary', primary.get('code', 'unknown'))}",
        "expected_effect": _expected_effect_for_cluster(str(primary.get("code", ""))),
        "evaluation_plan": "Re-run frozen, metamorphic, and retrieval benchmark manifests against the candidate skill file.",
        "change_summary": _change_summary_for_cluster(str(primary.get("code", ""))),
        "candidate_content": candidate_content,
    }


def _select_target_path(*, primary_code: str, allowed_targets: list[str]) -> str:
    target_map = {
        "high_duplicate_note_rate": "skills/resolve-identity/SKILL.md",
        "high_duplicate_cluster_count": "skills/resolve-identity/SKILL.md",
        "idempotence_failure": "skills/update-vault/SKILL.md",
        "high_graph_churn_rate": "skills/extract-knowledge/SKILL.md",
        "low_retrieval_qa_accuracy": "skills/extract-knowledge/SKILL.md",
        "low_retrieval_citation_hit_rate": "skills/extract-knowledge/SKILL.md",
        "high_isolated_note_rate": "skills/extract-knowledge/SKILL.md",
        "low_canonical_link_density": "skills/extract-knowledge/SKILL.md",
    }
    preferred = target_map.get(primary_code, "skills/extract-knowledge/SKILL.md")
    if preferred in allowed_targets:
        return preferred
    return allowed_targets[0]


def _apply_heuristic_edit(*, current_content: str, primary_code: str) -> str:
    updated = current_content
    if primary_code in {"high_isolated_note_rate", "low_canonical_link_density", "low_retrieval_qa_accuracy", "low_retrieval_citation_hit_rate"}:
        updated = _insert_unique_line(
            updated,
            section="Procedure",
            line="7. Prefer explicit cross-note relationships when the source clearly connects extracted people, concepts, projects, or topics.",
        )
        updated = _insert_unique_line(
            updated,
            section="Procedure",
            line="8. Preserve exact surface names and aliases that a later retrieval query is likely to use.",
        )
        updated = _insert_unique_line(
            updated,
            section="Guardrails",
            line="- do not emit placeholder relationships that add graph structure without source support",
        )
        return updated

    if primary_code in {"high_duplicate_note_rate", "high_duplicate_cluster_count"}:
        updated = _insert_unique_line(
            updated,
            section="Procedure",
            line="7. Treat close title, slug, and alias matches as merge candidates only after checking source context for compatibility.",
        )
        updated = _insert_unique_line(
            updated,
            section="Procedure",
            line="8. Prefer updating an existing canonical note over creating a near-duplicate when evidence strongly overlaps.",
        )
        return updated

    if primary_code == "high_graph_churn_rate":
        updated = _insert_unique_line(
            updated,
            section="Procedure",
            line="7. Ignore boilerplate or presentation-only text that does not add new source-grounded facts or relations.",
        )
        updated = _insert_unique_line(
            updated,
            section="Guardrails",
            line="- keep extraction stable across equivalent formatting and chunking changes",
        )
        return updated

    if primary_code == "idempotence_failure":
        updated = _insert_unique_line(
            updated,
            section="Procedure",
            line="7. Reuse existing sourced claims and aliases when the same source is re-ingested instead of rewriting equivalent content.",
        )
        return updated

    return _insert_unique_line(
        updated,
        section="Guardrails",
        line="- prefer bounded changes motivated by measured failures over broad rewrites",
    )


def _apply_candidate_skill_change(*, candidate_repo_root: Path, proposal: dict[str, Any]) -> None:
    target = candidate_repo_root / str(proposal["target_path"])
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(str(proposal["candidate_content"]).rstrip() + "\n", encoding="utf-8")


def _copy_accepted_skill_change(*, live_repo_root: Path, candidate_repo_root: Path, target_path: str) -> str:
    source = candidate_repo_root / target_path
    destination = live_repo_root / target_path
    destination.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
    return str(destination)


def _validate_target_path(target_path: str, allowed_targets: list[str]) -> None:
    if target_path not in allowed_targets:
        raise ValueError(f"Proposed target_path is not allowed: {target_path}")


def _insert_unique_line(content: str, *, section: str, line: str) -> str:
    if line in content:
        return content
    marker = f"## {section}\n"
    start = content.find(marker)
    if start == -1:
        return content.rstrip() + f"\n\n## {section}\n\n{line}\n"
    section_body_start = start + len(marker)
    next_heading = content.find("\n## ", section_body_start)
    if next_heading == -1:
        next_heading = len(content)
    before = content[:next_heading].rstrip("\n")
    after = content[next_heading:]
    return before + f"\n{line}\n" + after


def _classify_failure_message(message: str) -> tuple[str, str, int]:
    lower = message.lower()
    if "retrieval qa" in lower or "qa_" in lower:
        return "low_retrieval_qa_accuracy", "Retrieval QA is failing.", 85
    if "reingest" in lower or "idempot" in lower:
        return "idempotence_failure", "Re-ingestion stability is failing.", 88
    if "duplicate" in lower:
        return "high_duplicate_note_rate", "Duplicate handling is regressing.", 82
    if "graph_churn" in lower or "churn" in lower:
        return "high_graph_churn_rate", "Metamorphic stability is regressing.", 76
    if "canonical_link_density" in lower or "isolated_note_rate" in lower or "orphan_note_rate" in lower:
        return "high_isolated_note_rate", "Canonical graph connectivity is too weak.", 72
    if "hard_constraint" in lower or "issue_count" in lower:
        return "hard_constraint_failure", "Hard constraints are failing.", 95
    return "benchmark_failure", "Benchmark cases are failing for an uncategorized reason.", 60


def _maybe_add_metric_cluster(
    clusters: dict[str, dict[str, Any]],
    *,
    code: str,
    summary: str,
    priority: int,
    metric_name: str,
    metric_value: Any,
    threshold: Any,
    direction: str,
) -> None:
    if metric_value is None or threshold is None:
        return
    value = float(metric_value)
    limit = float(threshold)
    if direction == "max" and value <= limit:
        return
    if direction == "min" and value >= limit:
        return
    clusters.setdefault(
        code,
        {
            "code": code,
            "summary": summary,
            "priority": priority,
            "count": 1,
            "examples": [{"metric": metric_name, "value": value, "threshold": limit}],
            "suites": [],
        },
    )


def _append_numeric_sample(samples: dict[str, list[float]], key: str, value: Any) -> None:
    if value is None:
        return
    samples.setdefault(key, []).append(float(value))


def _compute_composite_score(aggregate: dict[str, Any]) -> float:
    weights = {
        "failed_case_count": -5.0,
        "hard_constraint_issue_count": -6.0,
        "citation_coverage": 1.2,
        "grounded_note_rate": 1.0,
        "canonical_link_density": 1.0,
        "duplicate_note_rate": -0.8,
        "duplicate_cluster_count": -0.2,
        "isolated_note_rate": -1.0,
        "unsupported_claim_rate": -1.2,
        "retrieval_qa_accuracy": 1.2,
        "retrieval_qa_note_hit_rate": 0.8,
        "retrieval_qa_citation_hit_rate": 0.8,
        "graph_churn_rate": -0.8,
    }
    score = 0.0
    for key, weight in weights.items():
        if key in aggregate and aggregate[key] is not None:
            score += float(aggregate[key]) * float(weight)
    return score


def _primary_cluster_requirement(*, cluster_code: str, comparison: dict[str, Any]) -> dict[str, Any] | None:
    if not cluster_code:
        return None
    floor = float(comparison.get("primary_metric_min_improvement", 0.0))
    mapping = {
        "hard_constraint_failure": {"metric": "hard_constraint_issue_count", "direction": "decrease", "min_delta": max(floor, 1.0)},
        "idempotence_failure": {"metric": "failed_case_count", "direction": "decrease", "min_delta": max(floor, 1.0)},
        "benchmark_failure": {"metric": "failed_case_count", "direction": "decrease", "min_delta": max(floor, 1.0)},
        "low_retrieval_qa_accuracy": {"metric": "retrieval_qa_accuracy", "direction": "increase", "min_delta": max(floor, 0.01)},
        "low_retrieval_citation_hit_rate": {"metric": "retrieval_qa_citation_hit_rate", "direction": "increase", "min_delta": max(floor, 0.01)},
        "high_graph_churn_rate": {"metric": "graph_churn_rate", "direction": "decrease", "min_delta": max(floor, 0.01)},
        "high_duplicate_note_rate": {"metric": "duplicate_note_rate", "direction": "decrease", "min_delta": max(floor, 0.001)},
        "high_duplicate_cluster_count": {"metric": "duplicate_cluster_count", "direction": "decrease", "min_delta": max(floor, 1.0)},
        "low_canonical_link_density": {"metric": "canonical_link_density", "direction": "increase", "min_delta": max(floor, 0.01)},
        "high_isolated_note_rate": {"metric": "isolated_note_rate", "direction": "decrease", "min_delta": max(floor, 0.01)},
    }
    return mapping.get(cluster_code)


def _check_primary_cluster_improvement(
    *,
    baseline: dict[str, Any],
    candidate: dict[str, Any],
    cluster_code: str,
    requirement: dict[str, Any] | None,
) -> str | None:
    if not requirement:
        return None
    metric = str(requirement.get("metric", "")).strip()
    direction = str(requirement.get("direction", "")).strip()
    min_delta = float(requirement.get("min_delta", 0.0))
    left = baseline.get(metric)
    right = candidate.get(metric)
    if left is None or right is None:
        return None

    if direction == "decrease":
        improvement = float(left) - float(right)
        if improvement >= min_delta:
            return f"primary cluster {cluster_code} improved via {metric} by {improvement:.4f}"
        return None

    if direction == "increase":
        improvement = float(right) - float(left)
        if improvement >= min_delta:
            return f"primary cluster {cluster_code} improved via {metric} by {improvement:.4f}"
        return None

    return None


def _reject_if_higher(
    reasons: list[str],
    key: str,
    baseline: dict[str, Any],
    candidate: dict[str, Any],
    allowed_regression: float,
) -> None:
    left = baseline.get(key)
    right = candidate.get(key)
    if left is None or right is None:
        return
    if float(right) > float(left) + allowed_regression:
        reasons.append(f"{key} regressed from {left} to {right}")


def _reject_if_lower(
    reasons: list[str],
    key: str,
    baseline: dict[str, Any],
    candidate: dict[str, Any],
    allowed_regression: float,
) -> None:
    left = baseline.get(key)
    right = candidate.get(key)
    if left is None or right is None:
        return
    if float(right) < float(left) - allowed_regression:
        reasons.append(f"{key} regressed from {left} to {right}")


def _note_improvement_if_lower(reasons: list[str], key: str, baseline: dict[str, Any], candidate: dict[str, Any]) -> None:
    left = baseline.get(key)
    right = candidate.get(key)
    if left is None or right is None:
        return
    if float(right) < float(left):
        reasons.append(f"{key} improved from {left} to {right}")


def _note_improvement_if_higher(reasons: list[str], key: str, baseline: dict[str, Any], candidate: dict[str, Any]) -> None:
    left = baseline.get(key)
    right = candidate.get(key)
    if left is None or right is None:
        return
    if float(right) > float(left):
        reasons.append(f"{key} improved from {left} to {right}")


def _expected_effect_for_cluster(code: str) -> str:
    effects = {
        "high_isolated_note_rate": "Increase explicit relationships between extracted notes so the canonical graph becomes less isolated.",
        "low_canonical_link_density": "Increase graph connectivity without sacrificing source grounding.",
        "low_retrieval_qa_accuracy": "Preserve more queryable names, aliases, and source-grounded relations for retrieval.",
        "low_retrieval_citation_hit_rate": "Preserve more source-grounded details that survive retrieval queries.",
        "high_duplicate_note_rate": "Reduce near-duplicate note creation by tightening merge guidance.",
        "high_duplicate_cluster_count": "Reduce duplicate clusters by improving identity-resolution caution and matching.",
        "high_graph_churn_rate": "Stabilize extraction under non-semantic text changes.",
        "idempotence_failure": "Reduce unnecessary rewrites when the same source is re-ingested.",
    }
    return effects.get(code, "Improve measured benchmark behavior without relaxing hard constraints.")


def _change_summary_for_cluster(code: str) -> str:
    summaries = {
        "high_isolated_note_rate": "Emphasize source-grounded cross-note relationships in extraction.",
        "low_canonical_link_density": "Emphasize connectivity-preserving relationship extraction.",
        "low_retrieval_qa_accuracy": "Emphasize exact names and aliases that help retrieval.",
        "low_retrieval_citation_hit_rate": "Emphasize preserving queryable sourced facts.",
        "high_duplicate_note_rate": "Emphasize cautious deduplication and merge preference.",
        "high_duplicate_cluster_count": "Emphasize title/alias/slug disambiguation before create.",
        "high_graph_churn_rate": "Emphasize invariance to boilerplate and formatting-only text.",
        "idempotence_failure": "Emphasize reuse of equivalent sourced content on re-ingest.",
    }
    return summaries.get(code, "Apply one bounded prompt-level refinement to the highest-priority skill.")


def _ledger_summary(result: dict[str, Any]) -> str:
    proposal = dict(result.get("proposal", {}))
    decision = dict(result.get("decision", {}))
    target = proposal.get("target_path", "unknown target")
    if result.get("status") == "accepted":
        return f"accepted self-update for {target}: {', '.join(decision.get('improvement_reasons', [])[:2])}"
    return f"rejected self-update for {target}: {', '.join(decision.get('rejection_reasons', [])[:2]) or 'no measurable improvement'}"


def _resolve_path(root: Path, path: Path) -> Path:
    return path if path.is_absolute() else (root / path)


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _run_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
