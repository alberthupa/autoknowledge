from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from autoknowledge.benchmarks import run_benchmark_manifest
from autoknowledge.diffing import summarize_diff
from autoknowledge.ingest import (
    apply_ingestion_plan,
    ingest_conversation,
    ingest_file,
    ingest_files_directory,
    save_plan,
)
from autoknowledge.indexer import index_vault, load_index, save_index
from autoknowledge.integrity import validate_index
from autoknowledge.ledger import append_record, tail_records
from autoknowledge.local_env import load_local_env
from autoknowledge.metrics import compute_metrics
from autoknowledge.providers import list_provider_models
from autoknowledge.retrieval_qa import load_question_set, run_question_set
from autoknowledge.runtime_config import load_runtime_config
from autoknowledge.self_update import run_self_update


def main() -> int:
    load_local_env()
    parser = argparse.ArgumentParser(description="AutoKnowledge thin harness")
    subparsers = parser.add_subparsers(dest="command", required=True)

    index_parser = subparsers.add_parser("index", help="Index a vault")
    index_parser.add_argument("--vault", required=True, help="Path to the vault root")
    index_parser.add_argument("--output", help="Optional path for the JSON snapshot")

    check_parser = subparsers.add_parser("check", help="Run integrity checks against a vault")
    check_parser.add_argument("--vault", required=True, help="Path to the vault root")

    metrics_parser = subparsers.add_parser("metrics", help="Compute integrity-backed metrics")
    metrics_parser.add_argument("--vault", required=True, help="Path to the vault root")

    diff_parser = subparsers.add_parser("diff", help="Compare two saved index snapshots")
    diff_parser.add_argument("--before", required=True, help="Earlier index JSON")
    diff_parser.add_argument("--after", required=True, help="Later index JSON")

    ingest_file_parser = subparsers.add_parser("ingest-file", help="Build or apply an ingestion plan for one file")
    ingest_file_parser.add_argument("--vault", required=True, help="Path to the target vault root")
    ingest_file_parser.add_argument("--input", required=True, help="Path to the input file")
    ingest_file_parser.add_argument("--origin", help="Optional source origin label")
    ingest_file_parser.add_argument("--title", help="Optional explicit title")
    ingest_file_parser.add_argument("--profile", help="Optional extractor profile override")
    ingest_file_parser.add_argument("--model", help="Optional model override inside the chosen profile")
    ingest_file_parser.add_argument("--config-root", default="config", help="Config directory root")
    ingest_file_parser.add_argument("--apply", action="store_true", help="Write planned changes to the vault")
    ingest_file_parser.add_argument("--plan-output", help="Optional path for saving the full plan JSON")

    ingest_conversation_parser = subparsers.add_parser(
        "ingest-conversation", help="Build or apply an ingestion plan for one conversation log"
    )
    ingest_conversation_parser.add_argument("--vault", required=True, help="Path to the target vault root")
    ingest_conversation_parser.add_argument("--input", required=True, help="Path to the conversation log")
    ingest_conversation_parser.add_argument("--origin", help="Optional source origin label")
    ingest_conversation_parser.add_argument("--title", help="Optional explicit title")
    ingest_conversation_parser.add_argument("--channel", help="Optional channel label")
    ingest_conversation_parser.add_argument("--profile", help="Optional extractor profile override")
    ingest_conversation_parser.add_argument("--model", help="Optional model override inside the chosen profile")
    ingest_conversation_parser.add_argument("--config-root", default="config", help="Config directory root")
    ingest_conversation_parser.add_argument("--apply", action="store_true", help="Write planned changes to the vault")
    ingest_conversation_parser.add_argument("--plan-output", help="Optional path for saving the full plan JSON")

    batch_parser = subparsers.add_parser("ingest-batch-files", help="Batch ingest a directory of files")
    batch_parser.add_argument("--vault", required=True, help="Path to the target vault root")
    batch_parser.add_argument("--input-dir", help="Directory to ingest; defaults to config/runtime.json")
    batch_parser.add_argument("--profile", help="Optional extractor profile override")
    batch_parser.add_argument("--model", help="Optional model override inside the chosen profile")
    batch_parser.add_argument("--config-root", default="config", help="Config directory root")
    batch_parser.add_argument("--apply", action="store_true", help="Write planned changes to the vault")
    batch_parser.add_argument("--limit", type=int, help="Optional maximum file count")
    batch_parser.add_argument("--glob", default="*.md", help="Glob pattern under the input dir")
    batch_parser.add_argument("--summary-output", help="Optional path for saving the batch summary JSON")
    batch_parser.add_argument("--plan-dir", help="Optional directory for per-file plan JSON files")

    list_models_parser = subparsers.add_parser("list-models", help="List available models for a provider")
    list_models_parser.add_argument("--provider", required=True, choices=["openai", "anthropic"], help="Provider name")

    benchmark_parser = subparsers.add_parser("benchmark-run", help="Run a benchmark manifest")
    benchmark_parser.add_argument("--manifest", required=True, help="Path to a benchmark manifest JSON file")
    benchmark_parser.add_argument("--profile", help="Optional profile override for all cases")
    benchmark_parser.add_argument("--model", help="Optional model override for all cases")
    benchmark_parser.add_argument("--config-root", default="config", help="Config directory root")
    benchmark_parser.add_argument("--keep-workdirs", action="store_true", help="Keep per-case temp workdirs for inspection")
    benchmark_parser.add_argument("--output", help="Optional path for saving the benchmark result JSON")

    qa_parser = subparsers.add_parser("qa-run", help="Run deterministic retrieval QA against a vault")
    qa_parser.add_argument("--vault", required=True, help="Path to the vault root")
    qa_parser.add_argument("--questions", required=True, help="Path to a question-set JSON file")
    qa_parser.add_argument("--scope", default="canonical", help="Search scope: canonical or managed")
    qa_parser.add_argument("--top-k", type=int, default=5, help="Number of top retrieval matches per question")
    qa_parser.add_argument("--output", help="Optional path for saving the QA result JSON")

    self_update_parser = subparsers.add_parser("self-update-run", help="Run one bounded self-update cycle")
    self_update_parser.add_argument("--policy", default="config/self_update.json", help="Self-update policy JSON")
    self_update_parser.add_argument("--config-root", default="config", help="Config directory root")
    self_update_parser.add_argument("--proposal-profile", help="Optional proposal profile override")
    self_update_parser.add_argument("--proposal-model", help="Optional proposal model override")
    self_update_parser.add_argument("--benchmark-profile", help="Optional benchmark profile override")
    self_update_parser.add_argument("--benchmark-model", help="Optional benchmark model override")
    self_update_parser.add_argument("--apply-accepted", action="store_true", help="Copy accepted candidate skill content back into the live repo")
    self_update_parser.add_argument("--keep-workdirs", action="store_true", help="Keep candidate and benchmark temp workdirs")

    ledger_parser = subparsers.add_parser("ledger", help="Append to or inspect the run ledger")
    ledger_subparsers = ledger_parser.add_subparsers(dest="ledger_command", required=True)

    ledger_append = ledger_subparsers.add_parser("append", help="Append one ledger record")
    ledger_append.add_argument("--path", default="state/ledger.jsonl", help="Ledger path")
    ledger_append.add_argument("--kind", required=True, help="Run kind, for example ingest or self-update")
    ledger_append.add_argument("--status", required=True, help="Run status")
    ledger_append.add_argument("--summary", required=True, help="Short summary")
    ledger_append.add_argument("--details-path", help="Optional details artifact path")
    ledger_append.add_argument("--metrics-path", help="Optional metrics artifact path")

    ledger_tail = ledger_subparsers.add_parser("tail", help="Show recent ledger records")
    ledger_tail.add_argument("--path", default="state/ledger.jsonl", help="Ledger path")
    ledger_tail.add_argument("--limit", type=int, default=10, help="Number of records to show")

    args = parser.parse_args()

    try:
        if args.command == "index":
            index = index_vault(Path(args.vault))
            if args.output:
                save_index(index, Path(args.output))
            print(json.dumps(index, indent=2, sort_keys=True))
            return 0

        if args.command == "check":
            index = index_vault(Path(args.vault))
            report = validate_index(index)
            print(json.dumps(report, indent=2, sort_keys=True))
            return 1 if report["issue_count"] else 0

        if args.command == "metrics":
            index = index_vault(Path(args.vault))
            report = validate_index(index)
            metrics = compute_metrics(index, report)
            print(json.dumps(metrics, indent=2, sort_keys=True))
            return 0

        if args.command == "diff":
            before = load_index(Path(args.before))
            after = load_index(Path(args.after))
            summary = summarize_diff(before, after)
            print(json.dumps(summary, indent=2, sort_keys=True))
            return 0

        if args.command == "ingest-file":
            plan = ingest_file(
                vault_root=Path(args.vault),
                input_path=Path(args.input),
                origin=args.origin,
                title=args.title,
                profile_name=args.profile,
                model_override=args.model,
                config_root=Path(args.config_root),
            )
            if args.plan_output:
                save_plan(plan, Path(args.plan_output))
            result = {"plan": plan.to_dict()}
            if args.apply:
                apply_result = apply_ingestion_plan(Path(args.vault), plan)
                check_index = index_vault(Path(args.vault))
                check_report = validate_index(check_index)
                result["apply"] = apply_result
                result["check"] = check_report
                print(json.dumps(result, indent=2, sort_keys=True))
                return 1 if check_report["issue_count"] else 0
            print(json.dumps(result, indent=2, sort_keys=True))
            return 0

        if args.command == "ingest-conversation":
            plan = ingest_conversation(
                vault_root=Path(args.vault),
                input_path=Path(args.input),
                origin=args.origin,
                title=args.title,
                channel=args.channel,
                profile_name=args.profile,
                model_override=args.model,
                config_root=Path(args.config_root),
            )
            if args.plan_output:
                save_plan(plan, Path(args.plan_output))
            result = {"plan": plan.to_dict()}
            if args.apply:
                apply_result = apply_ingestion_plan(Path(args.vault), plan)
                check_index = index_vault(Path(args.vault))
                check_report = validate_index(check_index)
                result["apply"] = apply_result
                result["check"] = check_report
                print(json.dumps(result, indent=2, sort_keys=True))
                return 1 if check_report["issue_count"] else 0
            print(json.dumps(result, indent=2, sort_keys=True))
            return 0

        if args.command == "ingest-batch-files":
            runtime = load_runtime_config(Path(args.config_root))
            input_dir = Path(args.input_dir) if args.input_dir else Path(runtime.get("paths", {}).get("default_batch_input_dir", "files"))
            summary = ingest_files_directory(
                vault_root=Path(args.vault),
                input_dir=input_dir,
                apply=args.apply,
                profile_name=args.profile or runtime.get("default_profiles", {}).get("batch"),
                model_override=args.model,
                config_root=Path(args.config_root),
                plan_dir=Path(args.plan_dir) if args.plan_dir else None,
                limit=args.limit,
                pattern=args.glob,
            )
            if args.summary_output:
                summary_output = Path(args.summary_output)
                summary_output.parent.mkdir(parents=True, exist_ok=True)
                summary_output.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            print(json.dumps(summary, indent=2, sort_keys=True))
            if args.apply and summary.get("check", {}).get("issue_count"):
                return 1
            return 0

        if args.command == "list-models":
            result = list_provider_models(args.provider)
            print(json.dumps(result, indent=2, sort_keys=True))
            return 0

        if args.command == "benchmark-run":
            result = run_benchmark_manifest(
                Path(args.manifest),
                profile_name=args.profile,
                model_override=args.model,
                config_root=Path(args.config_root),
                keep_workdirs=args.keep_workdirs,
            )
            if args.output:
                output_path = Path(args.output)
                output_path.parent.mkdir(parents=True, exist_ok=True)
                output_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            print(json.dumps(result, indent=2, sort_keys=True))
            return 0 if result.get("all_passed") else 1

        if args.command == "qa-run":
            index = index_vault(Path(args.vault))
            questions = load_question_set(Path(args.questions))
            result = run_question_set(
                index,
                questions,
                default_top_k=args.top_k,
                default_scope=args.scope,
            )
            if args.output:
                output_path = Path(args.output)
                output_path.parent.mkdir(parents=True, exist_ok=True)
                output_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            print(json.dumps(result, indent=2, sort_keys=True))
            return 0 if result.get("failed_count", 0) == 0 else 1

        if args.command == "self-update-run":
            result = run_self_update(
                policy_path=Path(args.policy),
                config_root=Path(args.config_root),
                proposal_profile_name=args.proposal_profile,
                proposal_model_override=args.proposal_model,
                benchmark_profile_name=args.benchmark_profile,
                benchmark_model_override=args.benchmark_model,
                apply_accepted=args.apply_accepted,
                keep_workdirs=args.keep_workdirs,
            )
            print(json.dumps(result, indent=2, sort_keys=True))
            return 0 if result.get("status") != "failed" else 1

        if args.command == "ledger":
            if args.ledger_command == "append":
                record = append_record(
                    Path(args.path),
                    kind=args.kind,
                    status=args.status,
                    summary=args.summary,
                    details_path=args.details_path,
                    metrics_path=args.metrics_path,
                )
                print(json.dumps(record, indent=2, sort_keys=True))
                return 0
            if args.ledger_command == "tail":
                records = tail_records(Path(args.path), limit=args.limit)
                print(json.dumps(records, indent=2, sort_keys=True))
                return 0
        parser.print_help()
        return 1
    except Exception as exc:
        print(json.dumps({"error": str(exc)}, indent=2, sort_keys=True))
        return 1


if __name__ == "__main__":
    sys.exit(main())
