"""Validation helpers for the documented runtime-to-skill contract."""

from __future__ import annotations

import ast
import json
from pathlib import Path
from typing import Any


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _load_contract(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _discover_cli_commands(main_path: Path) -> list[str]:
    tree = ast.parse(main_path.read_text(encoding="utf-8"), filename=str(main_path))
    commands: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if not isinstance(node.func, ast.Attribute) or node.func.attr != "add_parser":
            continue
        if not node.args or not isinstance(node.args[0], ast.Constant) or not isinstance(node.args[0].value, str):
            continue
        parser_name = node.args[0].value
        owner = node.func.value
        if isinstance(owner, ast.Name) and owner.id == "subparsers":
            commands.add(parser_name)
        elif isinstance(owner, ast.Name) and owner.id == "ledger_subparsers":
            commands.add(f"ledger {parser_name}")
    return sorted(commands)


def _discover_skills(skills_root: Path) -> list[str]:
    skill_names = [path.parent.name for path in sorted(skills_root.glob("*/SKILL.md"))]
    return sorted(skill_names)


def _scan_for_legacy_policy_refs(repo_root: Path) -> list[str]:
    guarded_paths = [
        repo_root / "README.md",
        repo_root / "AGENTS.md",
        repo_root / "skills" / "README.md",
        repo_root / "autoknowledge" / "providers.py",
    ]
    guarded_paths.extend(sorted((repo_root / "skills").glob("*/SKILL.md")))
    matches: list[str] = []
    for path in guarded_paths:
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8")
        if "agents.md" in text:
            matches.append(str(path.relative_to(repo_root)))
    return matches


def validate_runtime_contract(contract_path: Path, *, repo_root: Path | None = None) -> dict[str, Any]:
    root = repo_root or _repo_root()
    contract = _load_contract(contract_path)

    declared_commands = set(contract.get("commands", {}).keys())
    discovered_commands = set(_discover_cli_commands(root / "main.py"))
    undeclared_commands = sorted(discovered_commands - declared_commands)
    missing_commands = sorted(declared_commands - discovered_commands)

    declared_skills = set(contract.get("skills", {}).keys())
    discovered_skills = set(_discover_skills(root / "skills"))
    undeclared_skills = sorted(discovered_skills - declared_skills)
    missing_skills = sorted(declared_skills - discovered_skills)

    policy_file = contract.get("policy_file")
    policy_exists = bool(policy_file) and (root / str(policy_file)).exists()
    legacy_policy_refs = _scan_for_legacy_policy_refs(root) if policy_file == "AGENTS.md" else []

    issues: list[str] = []
    if not policy_exists:
        issues.append(f"Policy file is missing: {policy_file}")
    if undeclared_commands:
        issues.append(f"CLI commands missing from contract: {', '.join(undeclared_commands)}")
    if missing_commands:
        issues.append(f"Contract commands missing from CLI: {', '.join(missing_commands)}")
    if undeclared_skills:
        issues.append(f"Skills missing from contract: {', '.join(undeclared_skills)}")
    if missing_skills:
        issues.append(f"Contract skills missing on disk: {', '.join(missing_skills)}")
    if legacy_policy_refs:
        issues.append(f"Legacy policy-file references remain: {', '.join(legacy_policy_refs)}")

    return {
        "contract_path": str(contract_path),
        "policy_file": policy_file,
        "policy_exists": policy_exists,
        "discovered_commands": sorted(discovered_commands),
        "declared_commands": sorted(declared_commands),
        "undeclared_commands": undeclared_commands,
        "missing_commands": missing_commands,
        "discovered_skills": sorted(discovered_skills),
        "declared_skills": sorted(declared_skills),
        "undeclared_skills": undeclared_skills,
        "missing_skills": missing_skills,
        "legacy_policy_refs": legacy_policy_refs,
        "issue_count": len(issues),
        "issues": issues,
    }
