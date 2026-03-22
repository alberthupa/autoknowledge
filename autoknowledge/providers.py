"""Provider clients for live extraction backends and self-update proposals."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from json import JSONDecodeError
from typing import Any

from .repo_context import build_context_bundle, read_repo_text

EXTRACTION_CONTEXT_PATHS = [
    "agents.md",
    "skills/extract-knowledge/SKILL.md",
    "skills/resolve-identity/SKILL.md",
    "skills/update-vault/SKILL.md",
]

PROPOSAL_CONTEXT_PATHS = [
    "agents.md",
    "skills/propose-skill-change/SKILL.md",
    "skills/self-update-knowledge/SKILL.md",
    "skills/evaluate-graph/SKILL.md",
    "pitfalls.md",
]


def list_provider_models(provider: str) -> dict[str, Any]:
    provider = provider.lower()
    if provider == "openai":
        return _list_openai_models()
    if provider == "anthropic":
        return _list_anthropic_models()
    raise ValueError(f"Unsupported provider: {provider}")


def extract_with_provider(
    *,
    profile: dict[str, Any],
    input_kind: str,
    title: str,
    source_path: str,
    evidence_blocks: list[dict[str, Any]],
    window_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    backend = profile.get("backend")
    if backend == "openai_responses":
        return _openai_structured_extract(
            profile=profile,
            input_kind=input_kind,
            title=title,
            source_path=source_path,
            evidence_blocks=evidence_blocks,
            window_context=window_context,
        )
    if backend == "anthropic_messages":
        return _anthropic_structured_extract(
            profile=profile,
            input_kind=input_kind,
            title=title,
            source_path=source_path,
            evidence_blocks=evidence_blocks,
            window_context=window_context,
        )
    raise ValueError(f"Unsupported live backend: {backend}")


def propose_skill_change_with_provider(
    *,
    profile: dict[str, Any],
    policy: dict[str, Any],
    baseline_summary: dict[str, Any],
    failure_clusters: list[dict[str, Any]],
    allowed_targets: list[str],
) -> dict[str, Any]:
    backend = profile.get("backend")
    if backend == "openai_responses":
        return _openai_skill_change_proposal(
            profile=profile,
            policy=policy,
            baseline_summary=baseline_summary,
            failure_clusters=failure_clusters,
            allowed_targets=allowed_targets,
        )
    if backend == "anthropic_messages":
        return _anthropic_skill_change_proposal(
            profile=profile,
            policy=policy,
            baseline_summary=baseline_summary,
            failure_clusters=failure_clusters,
            allowed_targets=allowed_targets,
        )
    raise ValueError(f"Unsupported proposal backend: {backend}")


def _openai_structured_extract(
    *,
    profile: dict[str, Any],
    input_kind: str,
    title: str,
    source_path: str,
    evidence_blocks: list[dict[str, Any]],
    window_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    system_prompt, user_prompt = _build_extraction_prompts(
        input_kind=input_kind,
        title=title,
        source_path=source_path,
        evidence_blocks=evidence_blocks,
        window_context=window_context,
    )
    result, response = _run_openai_structured_json(
        profile=profile,
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        schema=_extraction_result_schema(),
        schema_name="extraction_result",
        label="structured extraction",
    )
    result["_provider_response"] = {
        "provider": "openai",
        "backend": profile.get("backend"),
        "model": profile.get("model"),
        "response_id": response.get("id"),
    }
    return result


def _anthropic_structured_extract(
    *,
    profile: dict[str, Any],
    input_kind: str,
    title: str,
    source_path: str,
    evidence_blocks: list[dict[str, Any]],
    window_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    system_prompt, user_prompt = _build_extraction_prompts(
        input_kind=input_kind,
        title=title,
        source_path=source_path,
        evidence_blocks=evidence_blocks,
        window_context=window_context,
    )
    result, response = _run_anthropic_structured_tool(
        profile=profile,
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        schema=_extraction_result_schema(),
        tool_name="emit_extraction",
        tool_description="Emit structured extraction candidates grounded in the supplied evidence blocks.",
        label="structured extraction",
    )
    result["_provider_response"] = {
        "provider": "anthropic",
        "backend": profile.get("backend"),
        "model": profile.get("model"),
        "response_id": response.get("id"),
    }
    return result


def _openai_skill_change_proposal(
    *,
    profile: dict[str, Any],
    policy: dict[str, Any],
    baseline_summary: dict[str, Any],
    failure_clusters: list[dict[str, Any]],
    allowed_targets: list[str],
) -> dict[str, Any]:
    system_prompt, user_prompt = _build_skill_change_proposal_prompts(
        policy=policy,
        baseline_summary=baseline_summary,
        failure_clusters=failure_clusters,
        allowed_targets=allowed_targets,
    )
    result, response = _run_openai_structured_json(
        profile=profile,
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        schema=_skill_change_proposal_schema(),
        schema_name="skill_change_proposal",
        label="skill change proposal",
    )
    result["_provider_response"] = {
        "provider": "openai",
        "backend": profile.get("backend"),
        "model": profile.get("model"),
        "response_id": response.get("id"),
    }
    return result


def _anthropic_skill_change_proposal(
    *,
    profile: dict[str, Any],
    policy: dict[str, Any],
    baseline_summary: dict[str, Any],
    failure_clusters: list[dict[str, Any]],
    allowed_targets: list[str],
) -> dict[str, Any]:
    system_prompt, user_prompt = _build_skill_change_proposal_prompts(
        policy=policy,
        baseline_summary=baseline_summary,
        failure_clusters=failure_clusters,
        allowed_targets=allowed_targets,
    )
    result, response = _run_anthropic_structured_tool(
        profile=profile,
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        schema=_skill_change_proposal_schema(),
        tool_name="emit_skill_change_proposal",
        tool_description="Emit one bounded proposal that replaces one allowed skill file.",
        label="skill change proposal",
    )
    result["_provider_response"] = {
        "provider": "anthropic",
        "backend": profile.get("backend"),
        "model": profile.get("model"),
        "response_id": response.get("id"),
    }
    return result


def _run_openai_structured_json(
    *,
    profile: dict[str, Any],
    system_prompt: str,
    user_prompt: str,
    schema: dict[str, Any],
    schema_name: str,
    label: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not set")

    base_url = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")
    options = profile.get("options", {})
    max_output_tokens = int(options.get("max_output_tokens", 4000))
    max_output_tokens_cap = int(options.get("max_output_tokens_cap", max_output_tokens))

    while True:
        body = {
            "model": profile["model"],
            "instructions": system_prompt,
            "input": user_prompt,
            "max_output_tokens": max_output_tokens,
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": schema_name,
                    "strict": True,
                    "schema": schema,
                }
            },
        }
        response = _json_request(
            f"{base_url.rstrip('/')}/responses",
            method="POST",
            headers={"Authorization": f"Bearer {api_key}"},
            body=body,
        )

        if _should_retry_openai_response(
            response=response,
            max_output_tokens=max_output_tokens,
            max_output_tokens_cap=max_output_tokens_cap,
        ):
            max_output_tokens = min(max_output_tokens * 2, max_output_tokens_cap)
            continue

        result = _parse_openai_json_response(response=response, label=label)
        return result, response


def _run_anthropic_structured_tool(
    *,
    profile: dict[str, Any],
    system_prompt: str,
    user_prompt: str,
    schema: dict[str, Any],
    tool_name: str,
    tool_description: str,
    label: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY is not set")

    base_url = os.environ.get("ANTHROPIC_BASE_URL", "https://api.anthropic.com/v1")
    anthropic_version = os.environ.get("ANTHROPIC_VERSION", "2023-06-01")
    body = {
        "model": profile["model"],
        "system": system_prompt,
        "max_tokens": profile.get("options", {}).get("max_output_tokens", 4000),
        "messages": [{"role": "user", "content": user_prompt}],
        "tools": [
            {
                "name": tool_name,
                "description": tool_description,
                "input_schema": schema,
            }
        ],
        "tool_choice": {"type": "tool", "name": tool_name},
    }
    response = _json_request(
        f"{base_url.rstrip('/')}/messages",
        method="POST",
        headers={
            "x-api-key": api_key,
            "anthropic-version": anthropic_version,
        },
        body=body,
    )

    for item in response.get("content", []):
        if item.get("type") == "tool_use" and item.get("name") == tool_name:
            return dict(item.get("input", {})), response

    text_parts: list[str] = []
    for item in response.get("content", []):
        if item.get("type") == "text":
            text_parts.append(item.get("text", ""))
    try:
        return json.loads("\n".join(text_parts)), response
    except JSONDecodeError as exc:
        preview = "\n".join(text_parts)[:200].replace("\n", "\\n")
        raise RuntimeError(f"Anthropic {label} returned invalid JSON: {preview!r}") from exc


def _list_openai_models() -> dict[str, Any]:
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not set")
    base_url = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")
    response = _json_request(
        f"{base_url.rstrip('/')}/models",
        method="GET",
        headers={"Authorization": f"Bearer {api_key}"},
        body=None,
    )
    ids = sorted(item["id"] for item in response.get("data", []) if "id" in item)
    return {"provider": "openai", "count": len(ids), "models": ids}


def _list_anthropic_models() -> dict[str, Any]:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY is not set")
    base_url = os.environ.get("ANTHROPIC_BASE_URL", "https://api.anthropic.com/v1")
    anthropic_version = os.environ.get("ANTHROPIC_VERSION", "2023-06-01")
    response = _json_request(
        f"{base_url.rstrip('/')}/models",
        method="GET",
        headers={
            "x-api-key": api_key,
            "anthropic-version": anthropic_version,
        },
        body=None,
    )
    ids = sorted(item["id"] for item in response.get("data", []) if "id" in item)
    return {"provider": "anthropic", "count": len(ids), "models": ids}


def _json_request(url: str, *, method: str, headers: dict[str, str], body: dict[str, Any] | None) -> dict[str, Any]:
    request_headers = {"content-type": "application/json", **headers}
    data = None if body is None else json.dumps(body).encode("utf-8")
    request = urllib.request.Request(url, data=data, headers=request_headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            payload = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        payload = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"{method} {url} failed: {exc.code} {payload}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"{method} {url} failed: {exc}") from exc
    return json.loads(payload)


def _extract_openai_text(response: dict[str, Any]) -> str:
    if isinstance(response.get("output_text"), str) and response.get("output_text"):
        return str(response["output_text"])
    text_parts: list[str] = []
    for output_item in response.get("output", []):
        if output_item.get("type") != "message":
            continue
        for content_item in output_item.get("content", []):
            if content_item.get("type") in {"output_text", "text"}:
                text_parts.append(content_item.get("text", ""))
    if not text_parts:
        raise RuntimeError("OpenAI response did not contain output text")
    return "\n".join(text_parts)


def _should_retry_openai_response(*, response: dict[str, Any], max_output_tokens: int, max_output_tokens_cap: int) -> bool:
    incomplete_details = response.get("incomplete_details") or {}
    reason = incomplete_details.get("reason")
    return (
        response.get("status") == "incomplete"
        and reason == "max_output_tokens"
        and max_output_tokens < max_output_tokens_cap
    )


def _parse_openai_json_response(*, response: dict[str, Any], label: str) -> dict[str, Any]:
    status = response.get("status")
    incomplete_details = response.get("incomplete_details") or {}
    incomplete_reason = incomplete_details.get("reason", "")

    if status == "incomplete":
        if incomplete_reason == "max_output_tokens":
            raise RuntimeError(
                f"OpenAI {label} was truncated by max_output_tokens. "
                "Increase the profile token budget or use a smaller input."
            )
        if incomplete_reason == "content_filter":
            raise RuntimeError(f"OpenAI {label} was halted by the content filter.")
        raise RuntimeError(f"OpenAI {label} is incomplete: {incomplete_reason or 'unknown reason'}")

    refusal = _extract_openai_refusal(response)
    if refusal:
        raise RuntimeError(f"OpenAI {label} refused the request: {refusal}")

    text = _extract_openai_text(response)
    try:
        return json.loads(text)
    except JSONDecodeError as exc:
        preview = text[:200].replace("\n", "\\n")
        raise RuntimeError(
            f"OpenAI {label} returned invalid JSON "
            f"(status={status or 'unknown'}, response_id={response.get('id', '')}, preview={preview!r})"
        ) from exc


def _extract_openai_refusal(response: dict[str, Any]) -> str | None:
    for output_item in response.get("output", []):
        if output_item.get("type") != "message":
            continue
        for content_item in output_item.get("content", []):
            if content_item.get("type") == "refusal":
                return str(content_item.get("refusal", "")).strip() or "refused"
    return None


def _build_extraction_prompts(
    *,
    input_kind: str,
    title: str,
    source_path: str,
    evidence_blocks: list[dict[str, Any]],
    window_context: dict[str, Any] | None = None,
) -> tuple[str, str]:
    skill_context = build_context_bundle(EXTRACTION_CONTEXT_PATHS, max_chars=18000)
    system_prompt = (
        "You execute the live extraction stage of AutoKnowledge.\n"
        "Return only JSON matching the schema.\n"
        "Use only the supplied evidence blocks.\n"
        "This request may cover only one window of a larger source.\n"
        "Prefer fewer, higher-confidence notes over many weak notes.\n"
        "Every claim and relationship must use a supplied source_ref.\n"
        "Use note_type unresolved when identity is ambiguous.\n"
        "Do not duplicate the same idea across multiple candidates without evidence.\n"
        "Prefer stable surface forms from the evidence for titles and aliases.\n"
        "Treat appendices, export footers, mailing metadata, legal boilerplate, and archival markers as low-information context unless they contain clear repeated domain facts.\n"
        "Do not create notes whose only support comes from appendix or footer language.\n"
        "Ignore section labels, export labels, and presentation-only wrappers when they do not add source-grounded facts.\n"
        "Do not invent temporary placeholder names, single-letter titles, or diagram-node labels as standalone notes.\n"
        "If a person, tool, or concept is clearly named in the evidence, prefer that exact source-grounded name over a renamed variant.\n"
        "Apply the repo policy and skill guidance below when choosing what to extract.\n\n"
        f"{skill_context}"
    )
    payload = {
        "task": "Extract note candidates from the source.",
        "input_kind": input_kind,
        "title": title,
        "source_path": source_path,
        "evidence_blocks": evidence_blocks,
        "instructions": {
            "allowed_note_types": ["entity", "concept", "topic", "unresolved"],
            "allowed_confidence": ["high", "medium", "low"],
            "claims_should_be_atomic": True,
            "prefer_relationships_when_unsure": True,
            "do_not_invent_unsourced_facts": True,
        },
    }
    if window_context:
        payload["window_context"] = window_context
    user_prompt = json.dumps(payload, ensure_ascii=True)
    return system_prompt, user_prompt


def _build_skill_change_proposal_prompts(
    *,
    policy: dict[str, Any],
    baseline_summary: dict[str, Any],
    failure_clusters: list[dict[str, Any]],
    allowed_targets: list[str],
) -> tuple[str, str]:
    proposal_context = build_context_bundle(PROPOSAL_CONTEXT_PATHS, max_chars=18000)
    system_prompt = (
        "You propose one bounded AutoKnowledge skill edit.\n"
        "Return only JSON matching the schema.\n"
        "Choose exactly one target_path from allowed_targets.\n"
        "candidate_content must be the full replacement content for that skill file.\n"
        "Prefer the smallest change that addresses the highest-value failure cluster.\n"
        "Do not relax hard constraints and do not propose multi-file edits.\n"
        "Keep the proposal grounded in measured failures and benchmark behavior.\n\n"
        f"{proposal_context}"
    )
    payload = {
        "task": "Propose one bounded skill-file replacement.",
        "allowed_targets": allowed_targets,
        "baseline_summary": baseline_summary,
        "failure_clusters": failure_clusters,
        "comparison_policy": policy.get("comparison", {}),
        "warning_thresholds": policy.get("warning_thresholds", {}),
        "current_skill_files": {target: read_repo_text(target) for target in allowed_targets},
    }
    return system_prompt, json.dumps(payload, ensure_ascii=True)


def _extraction_result_schema() -> dict[str, Any]:
    candidate_schema = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "note_type": {
                "type": "string",
                "enum": ["entity", "concept", "topic", "unresolved"],
            },
            "title": {"type": "string", "minLength": 1},
            "canonical_slug": {"type": "string", "minLength": 1},
            "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
            "aliases": {"type": "array", "items": {"type": "string"}},
            "kind": {"type": "string"},
            "claims": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "text": {"type": "string", "minLength": 1},
                        "source_ref": {"type": "string", "minLength": 1},
                        "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
                    },
                    "required": ["text", "source_ref", "confidence"],
                },
            },
            "relationships": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "text": {"type": "string", "minLength": 1},
                        "source_ref": {"type": "string", "minLength": 1},
                        "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
                    },
                    "required": ["text", "source_ref", "confidence"],
                },
            },
        },
        "required": [
            "note_type",
            "title",
            "canonical_slug",
            "confidence",
            "aliases",
            "kind",
            "claims",
            "relationships",
        ],
    }
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "note_candidates": {"type": "array", "items": candidate_schema},
            "unresolved_candidates": {"type": "array", "items": candidate_schema},
        },
        "required": ["note_candidates", "unresolved_candidates"],
    }


def _skill_change_proposal_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "target_path": {"type": "string", "minLength": 1},
            "rationale": {"type": "string", "minLength": 1},
            "expected_effect": {"type": "string", "minLength": 1},
            "evaluation_plan": {"type": "string", "minLength": 1},
            "change_summary": {"type": "string", "minLength": 1},
            "candidate_content": {"type": "string", "minLength": 1},
        },
        "required": [
            "target_path",
            "rationale",
            "expected_effect",
            "evaluation_plan",
            "change_summary",
            "candidate_content",
        ],
    }
