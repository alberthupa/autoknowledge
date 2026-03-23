"""Deterministic source-grounded retrieval QA over an indexed vault."""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .contracts import CANONICAL_TYPES

WIKI_LINK_RE = re.compile(r"\[\[([^\]]+)\]\]")
SOURCE_REF_RE = re.compile(r"\[\[([^\]]+#\^[A-Za-z0-9_-]+)\]\]")
SOURCE_CLAUSE_RE = re.compile(r"\s+Source:\s*\[\[[^\]]+\]\]")
CONFIDENCE_CLAUSE_RE = re.compile(r"\s+Confidence:\s*[A-Za-z]+")
TOKEN_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]*")

QUESTION_STOPWORDS = {
    "a",
    "an",
    "and",
    "answer",
    "as",
    "at",
    "be",
    "by",
    "canonical",
    "do",
    "does",
    "file",
    "for",
    "from",
    "how",
    "in",
    "is",
    "it",
    "its",
    "mentioned",
    "note",
    "of",
    "on",
    "or",
    "overview",
    "question",
    "source",
    "that",
    "the",
    "there",
    "this",
    "to",
    "vault",
    "what",
    "where",
    "which",
    "who",
}


@dataclass
class FactRecord:
    note_path: str
    note_title: str
    note_type: str
    fact_text: str
    rendered_text: str
    source_refs: list[str]
    note_tokens: set[str]
    fact_tokens: set[str]


def load_question_set(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        questions = payload.get("questions")
        if isinstance(questions, list):
            return questions
    raise ValueError(f"Unsupported question set format: {path}")


def run_question_set(
    index: dict[str, Any],
    questions: list[dict[str, Any]],
    *,
    default_top_k: int = 5,
    default_scope: str = "canonical",
) -> dict[str, Any]:
    results = [
        _run_single_question(
            index=index,
            question_spec=question_spec,
            default_top_k=default_top_k,
            default_scope=default_scope,
        )
        for question_spec in questions
    ]

    passed_count = sum(1 for item in results if item["passed"])
    note_checks = [item["note_hit"] for item in results if item["note_hit"] is not None]
    citation_checks = [item["citation_hit"] for item in results if item["citation_hit"] is not None]
    question_count = len(results)
    failed_count = question_count - passed_count

    return {
        "question_count": question_count,
        "passed_count": passed_count,
        "failed_count": failed_count,
        "accuracy": passed_count / max(question_count, 1),
        "note_hit_rate": sum(1 for value in note_checks if value) / max(len(note_checks), 1),
        "citation_hit_rate": sum(1 for value in citation_checks if value) / max(len(citation_checks), 1),
        "questions": results,
    }


def answer_question(
    index: dict[str, Any],
    question: str,
    *,
    top_k: int = 5,
    scope: str = "canonical",
) -> dict[str, Any]:
    facts = _build_fact_index(index, scope=scope)
    question_tokens = _tokenize_question(question)
    normalized_question = _normalize_phrase(question)
    scored = []

    for fact in facts:
        score = _score_fact(
            fact=fact,
            question_tokens=question_tokens,
            normalized_question=normalized_question,
        )
        if score <= 0:
            continue
        scored.append((score, fact))

    scored.sort(
        key=lambda item: (
            -item[0],
            item[1].note_path,
            item[1].rendered_text,
        )
    )
    ranked = _select_ranked_facts(scored, top_k=top_k)
    matches = []
    for rank, (score, fact) in enumerate(ranked, start=1):
        matches.append(
            {
                "rank": rank,
                "score": score,
                "note_path": fact.note_path,
                "note_title": fact.note_title,
                "note_type": fact.note_type,
                "fact_text": fact.fact_text,
                "rendered_text": fact.rendered_text,
                "source_refs": list(fact.source_refs),
            }
        )

    return {
        "question": question,
        "top_k": top_k,
        "scope": scope,
        "match_count": len(matches),
        "matches": matches,
        "answer": "\n".join(f"- {item['rendered_text']}" for item in matches),
    }


def _run_single_question(
    *,
    index: dict[str, Any],
    question_spec: dict[str, Any],
    default_top_k: int,
    default_scope: str,
) -> dict[str, Any]:
    question_id = str(question_spec.get("id", "question"))
    question = str(question_spec.get("question", "")).strip()
    if not question:
        raise ValueError(f"Question {question_id!r} is missing text")

    top_k = int(question_spec.get("top_k", default_top_k))
    scope = str(question_spec.get("scope", default_scope))
    answer = answer_question(index, question, top_k=top_k, scope=scope)
    expectations = dict(question_spec.get("expect", {}))
    failures, note_hit, citation_hit = _evaluate_question(expectations=expectations, answer=answer)
    return {
        "id": question_id,
        "question": question,
        "top_k": top_k,
        "scope": scope,
        "passed": not failures,
        "failures": failures,
        "note_hit": note_hit,
        "citation_hit": citation_hit,
        "answer": answer["answer"],
        "matches": answer["matches"],
        "match_count": answer["match_count"],
    }


def _build_fact_index(index: dict[str, Any], *, scope: str) -> list[FactRecord]:
    notes = index.get("notes", [])
    facts: list[FactRecord] = []

    for note in notes:
        if scope == "canonical" and note["note_type"] not in CANONICAL_TYPES:
            continue
        if scope == "managed" and not note["note_type"]:
            continue
        bullets = list(note.get("claim_bullets", [])) + list(note.get("relationship_bullets", []))
        if not bullets:
            continue

        note_tokens = set(_tokenize_text(note.get("title", "")))
        for bullet in bullets:
            cleaned = _clean_bullet_text(bullet)
            source_refs = _extract_source_refs(bullet)
            fact_tokens = set(_tokenize_text(cleaned))
            facts.append(
                FactRecord(
                    note_path=note["path"],
                    note_title=str(note.get("title") or note.get("stem") or note["path"]),
                    note_type=note["note_type"],
                    fact_text=cleaned,
                    rendered_text=f"{note.get('title') or note.get('stem')}: {cleaned}",
                    source_refs=source_refs,
                    note_tokens=note_tokens,
                    fact_tokens=fact_tokens,
                )
            )
    return facts


def _score_fact(
    *,
    fact: FactRecord,
    question_tokens: set[str],
    normalized_question: str,
) -> int:
    if not question_tokens:
        return 0

    note_overlap = len(question_tokens & fact.note_tokens)
    fact_overlap = len(question_tokens & fact.fact_tokens)
    score = note_overlap * 5 + fact_overlap * 3

    note_phrase = _normalize_phrase(fact.note_title)
    if note_phrase and note_phrase in normalized_question:
        score += 12 + len(fact.note_tokens)
    if fact.note_tokens and fact.note_tokens.issubset(question_tokens):
        score += 8 + len(fact.note_tokens)
    if "mentioned" in normalized_question and fact.fact_text.lower().startswith("mentioned_in"):
        score += 20
    elif "mentioned" in normalized_question and "mentioned" in fact.fact_text.lower():
        score += 8
    if "mentioned" in normalized_question and fact.note_type == "entity":
        score += 3
    if "source" in normalized_question and fact.source_refs:
        score += 1
    return score


def _select_ranked_facts(scored: list[tuple[int, FactRecord]], *, top_k: int) -> list[tuple[int, FactRecord]]:
    primary: list[tuple[int, FactRecord]] = []
    used_note_paths: set[str] = set()
    used_keys: set[tuple[str, str]] = set()

    for item in scored:
        key = (item[1].note_path, item[1].fact_text)
        if key in used_keys:
            continue
        if item[1].note_path in used_note_paths:
            continue
        primary.append(item)
        used_note_paths.add(item[1].note_path)
        used_keys.add(key)
        if len(primary) >= top_k:
            return primary

    for item in scored:
        key = (item[1].note_path, item[1].fact_text)
        if key in used_keys:
            continue
        primary.append(item)
        used_keys.add(key)
        if len(primary) >= top_k:
            break
    return primary


def _evaluate_question(
    *,
    expectations: dict[str, Any],
    answer: dict[str, Any],
) -> tuple[list[str], bool | None, bool | None]:
    failures: list[str] = []
    matches = list(answer.get("matches", []))
    matched_note_paths = [str(item["note_path"]) for item in matches]
    matched_source_refs = [_normalize_source_ref(ref) for item in matches for ref in item.get("source_refs", [])]
    matched_source_blocks = [_source_block_id(ref) for ref in matched_source_refs if _source_block_id(ref)]
    answer_text = str(answer.get("answer", ""))

    note_hit: bool | None = None
    citation_hit: bool | None = None

    expected_note_paths_any = list(expectations.get("expected_note_paths_any", []))
    expected_note_paths_all = list(expectations.get("expected_note_paths_all", []))
    if expected_note_paths_any:
        note_hit = any(path in matched_note_paths for path in expected_note_paths_any)
        if not note_hit:
            failures.append(f"expected any note path from {expected_note_paths_any}, got {matched_note_paths}")
    if expected_note_paths_all:
        note_hit = all(path in matched_note_paths for path in expected_note_paths_all)
        if not note_hit:
            failures.append(f"expected all note paths {expected_note_paths_all}, got {matched_note_paths}")

    expected_source_refs_any = [_normalize_source_ref(value) for value in expectations.get("expected_source_refs_any", [])]
    expected_source_refs_all = [_normalize_source_ref(value) for value in expectations.get("expected_source_refs_all", [])]
    expected_source_blocks_any = [str(value) for value in expectations.get("expected_source_block_ids_any", [])]
    expected_source_blocks_all = [str(value) for value in expectations.get("expected_source_block_ids_all", [])]
    expected_source_paths_any = [str(value) for value in expectations.get("expected_source_path_contains_any", [])]
    expected_source_paths_all = [str(value) for value in expectations.get("expected_source_path_contains_all", [])]

    has_citation_expectation = any(
        [
            expected_source_refs_any,
            expected_source_refs_all,
            expected_source_blocks_any,
            expected_source_blocks_all,
            expected_source_paths_any,
            expected_source_paths_all,
        ]
    )
    if has_citation_expectation:
        citation_hit = True

    if expected_source_refs_any:
        hit = any(ref in matched_source_refs for ref in expected_source_refs_any)
        citation_hit = citation_hit and hit if citation_hit is not None else hit
        if not hit:
            failures.append(f"expected any source ref from {expected_source_refs_any}, got {matched_source_refs}")
    if expected_source_refs_all:
        hit = all(ref in matched_source_refs for ref in expected_source_refs_all)
        citation_hit = citation_hit and hit if citation_hit is not None else hit
        if not hit:
            failures.append(f"expected all source refs {expected_source_refs_all}, got {matched_source_refs}")
    if expected_source_blocks_any:
        hit = any(block_id in matched_source_blocks for block_id in expected_source_blocks_any)
        citation_hit = citation_hit and hit if citation_hit is not None else hit
        if not hit:
            failures.append(f"expected any source block id from {expected_source_blocks_any}, got {matched_source_blocks}")
    if expected_source_blocks_all:
        hit = all(block_id in matched_source_blocks for block_id in expected_source_blocks_all)
        citation_hit = citation_hit and hit if citation_hit is not None else hit
        if not hit:
            failures.append(f"expected all source block ids {expected_source_blocks_all}, got {matched_source_blocks}")
    if expected_source_paths_any:
        hit = any(any(fragment in ref for ref in matched_source_refs) for fragment in expected_source_paths_any)
        citation_hit = citation_hit and hit if citation_hit is not None else hit
        if not hit:
            failures.append(
                f"expected any source path fragment from {expected_source_paths_any}, got {matched_source_refs}"
            )
    if expected_source_paths_all:
        hit = all(any(fragment in ref for ref in matched_source_refs) for fragment in expected_source_paths_all)
        citation_hit = citation_hit and hit if citation_hit is not None else hit
        if not hit:
            failures.append(
                f"expected all source path fragments {expected_source_paths_all}, got {matched_source_refs}"
            )

    answer_contains_all = [str(value) for value in expectations.get("answer_contains_all", [])]
    for fragment in answer_contains_all:
        if fragment not in answer_text:
            failures.append(f"expected answer to contain {fragment!r}, got {answer_text!r}")

    min_match_count = expectations.get("min_match_count")
    if min_match_count is not None and int(answer.get("match_count", 0)) < int(min_match_count):
        failures.append(f"expected match_count >= {min_match_count}, got {answer.get('match_count')}")

    return failures, note_hit, citation_hit


def _clean_bullet_text(value: str) -> str:
    text = value.strip()
    if text.startswith("- "):
        text = text[2:]
    text = SOURCE_CLAUSE_RE.sub("", text)
    text = CONFIDENCE_CLAUSE_RE.sub("", text)
    text = _replace_wiki_links(text)
    return " ".join(text.split()).strip()


def _replace_wiki_links(value: str) -> str:
    def repl(match: re.Match[str]) -> str:
        target = match.group(1)
        if "|" in target:
            target = target.split("|", 1)[0]
        target = target.split("#", 1)[0]
        leaf = target.split("/")[-1]
        if leaf.endswith(".md"):
            leaf = leaf[:-3]
        if re.match(r"\d{4}-\d{2}-\d{2}--.+--(?:src|conv)_[A-Za-z0-9]+$", leaf):
            leaf = re.sub(r"^\d{4}-\d{2}-\d{2}--", "", leaf)
            leaf = re.sub(r"--(?:src|conv)_[A-Za-z0-9]+$", "", leaf)
        return leaf.replace("-", " ")

    return WIKI_LINK_RE.sub(repl, value)


def _extract_source_refs(value: str) -> list[str]:
    refs = []
    for ref in SOURCE_REF_RE.findall(value):
        normalized = _normalize_source_ref(ref)
        if "sources/" in normalized:
            refs.append(normalized)
    return refs


def _tokenize_question(value: str) -> set[str]:
    return {token for token in _tokenize_text(value) if token not in QUESTION_STOPWORDS}


def _tokenize_text(value: str) -> list[str]:
    return [token.lower().replace("_", "-") for token in TOKEN_RE.findall(value)]


def _normalize_phrase(value: str) -> str:
    return " ".join(_tokenize_text(value))


def _normalize_source_ref(value: str) -> str:
    text = value.strip()
    if text.startswith("[[") and text.endswith("]]"):
        text = text[2:-2]
    return text


def _source_block_id(value: str) -> str | None:
    text = _normalize_source_ref(value)
    if "#^" not in text:
        return None
    return text.split("#^", 1)[1]


__all__ = [
    "answer_question",
    "load_question_set",
    "run_question_set",
]
