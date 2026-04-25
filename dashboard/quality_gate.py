#!/usr/bin/env python3
"""Deterministic quality gate for generated article artifacts."""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse, urlunparse

WEAK_BYLINE_TOKENS = {
    "admin",
    "author",
    "blog",
    "company",
    "editor",
    "editorial",
    "granola",
    "marketing",
    "newsroom",
    "staff",
    "team",
}
WEAK_ROLE_TOKENS = {"and", "author", "blog", "none", "null", "staff", "team", "the", "unknown"}
SINGLE_NAME_ROLE_KEYWORDS = {
    "architect",
    "ceo",
    "chief",
    "cofounder",
    "cto",
    "developer",
    "director",
    "engineer",
    "engineering",
    "founder",
    "head",
    "lead",
    "manager",
    "product",
    "software",
}
SECURITY_ROLE_KEYWORDS = {"compliance", "governance", "legal", "privacy", "risk", "security", "trust"}
REVIEWER_ROLE_KEYWORDS = {"ceo", "chief", "cofounder", "founder", "head", "lead", "product"}
INTENT_REQUIREMENTS = {
    "category": {
        "minimum_total_sources": 4,
        "minimum_external_sources": 1,
        "minimum_internal_sources": 2,
        "minimum_inline_references": 2,
    },
    "security": {
        "minimum_total_sources": 5,
        "minimum_external_sources": 2,
        "minimum_internal_sources": 2,
        "minimum_inline_references": 3,
    },
    "workflow": {
        "minimum_total_sources": 5,
        "minimum_external_sources": 2,
        "minimum_internal_sources": 2,
        "minimum_inline_references": 3,
    },
}
JSON_STRINGISH_PREFIXES = tuple('{["-0123456789tfn')
SCOPE_DRIFT_STOPWORDS = {
    "about", "after", "also", "and", "best", "blog", "built", "from", "gets", "got",
    "have", "into", "its", "just", "more", "over", "that", "than", "their", "there",
    "they", "this", "what", "when", "where", "which", "with", "your",
}


def _coerce_json_payload(value: Any) -> Any:
    current = value
    for _ in range(4):
        if not isinstance(current, str):
            return current
        candidate = current.strip()
        if not candidate or candidate[0].lower() not in JSON_STRINGISH_PREFIXES:
            return current
        try:
            current = json.loads(candidate)
        except json.JSONDecodeError:
            return current
    return current


def _load_json(path: Path) -> Any:
    return _coerce_json_payload(json.loads(path.read_text(encoding="utf-8")))


def _load_required_json(path: Path, label: str) -> Any:
    if not path.exists():
        raise ValueError(f"{label} is required but missing: {path}")
    return _load_json(path)


def _read_required_text(path: Path, label: str) -> str:
    if not path.exists():
        raise ValueError(f"{label} is required but missing: {path}")
    text = path.read_text(encoding="utf-8")
    if not text.strip():
        raise ValueError(f"{label} is required but empty: {path}")
    return text


def _require_mapping(value: Any, label: str, path: Path) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    raise ValueError(f"{label} must be a JSON object: {path}")


def _coerce_audit_score(value: Any) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        score = int(value)
    except (TypeError, ValueError):
        return None
    return max(0, min(40, score))


def _first_audit_score(*values: Any) -> int | None:
    for value in values:
        score = _coerce_audit_score(value)
        if score is not None:
            return score
    return None


def _normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def _looks_like_faq_question(text: str) -> bool:
    normalized = _normalize_text(text)
    if not normalized:
        return False
    if normalized.endswith("?"):
        return True
    return bool(re.match(r"^(how|what|when|where|which|who|why|can|could|should|do|does|is|are|will)\b", normalized, re.IGNORECASE))


def _canonicalize_url(url: str, base_url: str | None = None) -> str:
    if not url:
        return ""
    resolved = urljoin(base_url or "", url)
    parsed = urlparse(resolved)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return ""
    path = parsed.path or "/"
    if path != "/" and path.endswith("/"):
        path = path[:-1]
    return urlunparse(parsed._replace(
        scheme=parsed.scheme.lower(),
        netloc=parsed.netloc.lower(),
        path=path,
        params="",
        query="",
        fragment="",
    ))


def _type_names(value: Any) -> set[str]:
    names: set[str] = set()
    if isinstance(value, dict):
        raw = value.get("@type")
        if isinstance(raw, str):
            names.add(raw)
        elif isinstance(raw, list):
            names.update(item for item in raw if isinstance(item, str))
        for child in value.values():
            names.update(_type_names(child))
    elif isinstance(value, list):
        for item in value:
            names.update(_type_names(item))
    return names


def _walk_nodes(value: Any) -> list[dict[str, Any]]:
    nodes: list[dict[str, Any]] = []
    if isinstance(value, dict):
        nodes.append(value)
        for child in value.values():
            nodes.extend(_walk_nodes(child))
    elif isinstance(value, list):
        for item in value:
            nodes.extend(_walk_nodes(item))
    return nodes


def _has_type(node: dict[str, Any], expected: str) -> bool:
    raw = node.get("@type")
    if isinstance(raw, str):
        return raw == expected
    if isinstance(raw, list):
        return expected in raw
    return False


def _slug_tokens(value: str) -> list[str]:
    return re.findall(r"[A-Za-z][A-Za-z'-]+", value or "")


def _topic_tokens(*values: str) -> list[str]:
    tokens: list[str] = []
    for value in values:
        for token in _slug_tokens(value):
            lowered = token.lower()
            if len(lowered) < 4 or lowered in SCOPE_DRIFT_STOPWORDS:
                continue
            tokens.append(lowered)
    return _dedupe_preserve(tokens)


def _is_weak_byline(name: str) -> bool:
    tokens = _slug_tokens(name)
    if len(tokens) < 2:
        return True
    lowered = {token.lower() for token in tokens}
    return bool(lowered & WEAK_BYLINE_TOKENS)


def _has_first_and_last_name(name: str) -> bool:
    return not _is_weak_byline(name)


def _is_real_single_name_role(role: str) -> bool:
    normalized = _normalize_text(role).lower()
    if len(normalized) < 4 or normalized in WEAK_ROLE_TOKENS:
        return False
    role_tokens = {token.lower() for token in _slug_tokens(role)}
    if role_tokens & WEAK_ROLE_TOKENS:
        return False
    return bool(role_tokens & SINGLE_NAME_ROLE_KEYWORDS)


def _is_single_name_with_role(name: str, role: str) -> bool:
    name_tokens = _slug_tokens(name)
    if len(name_tokens) != 1:
        return False
    if name_tokens[0].lower() in WEAK_BYLINE_TOKENS:
        return False
    return _is_real_single_name_role(role)


def _dedupe_preserve(values: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        if not value or value in seen:
            continue
        seen.add(value)
        ordered.append(value)
    return ordered


def _infer_intent(article: dict[str, Any], recommendations: dict[str, Any], evidence: dict[str, Any]) -> str:
    explicit = evidence.get("intent_class")
    if isinstance(explicit, str) and explicit:
        return explicit
    haystack = " ".join([
        str(recommendations.get("article_type", "")),
        str(article.get("slug", "")),
        str(article.get("title", "")),
        str(article.get("body_md", ""))[:2000],
    ]).lower()
    if any(keyword in haystack for keyword in ("soc2", "security", "privacy", "subprocessor", "dpa", "saml", "sso")):
        return "security"
    if any(keyword in haystack for keyword in ("workflow", "zapier", "crm", "hubspot", "linear", "notion", "apps", "integration")):
        return "workflow"
    return "category"


def _scope_drift_check(
    article: dict[str, Any],
    recommendations: dict[str, Any],
    snapshot: HTMLSnapshot,
) -> dict[str, Any]:
    visible_h1 = next((item["text"] for item in snapshot.headings if item["level"] == 1), "")
    source_title = str((recommendations.get("captured_article") or {}).get("title") or article.get("title") or "")
    source_slug = str(article.get("slug") or "")
    source_entities = [
        str(item).strip().lower()
        for item in (((article.get("trust") or {}).get("entities_mentioned")) or [])
        if isinstance(item, str) and item.strip()
    ]
    rewritten_title = visible_h1 or snapshot.title
    rewritten_context = " ".join(
        [rewritten_title] +
        [str(item.get("text") or "") for item in snapshot.headings[:4]]
    )
    source_tokens = _topic_tokens(source_title, source_slug)
    rewritten_tokens = _topic_tokens(rewritten_context)
    overlap_tokens = [token for token in source_tokens if token in rewritten_tokens]

    matched_prompts = recommendations.get("matched_prompts")
    prompt_tokens: list[str] = []
    if isinstance(matched_prompts, list):
        for item in matched_prompts[:2]:
            if not isinstance(item, dict):
                continue
            prompt_tokens.extend(_topic_tokens(str(item.get("prompt_text") or "")))
    prompt_tokens = _dedupe_preserve(prompt_tokens)
    prompt_overlap_tokens = [token for token in prompt_tokens if token in rewritten_tokens]

    visible_text = snapshot.visible_text.lower()
    missing_entities = [entity for entity in _dedupe_preserve(source_entities) if entity not in visible_text]

    topic_overlap_ratio = len(overlap_tokens) / max(len(source_tokens), 1)
    status = "passed"
    detail = "Rewrite keeps the original topic anchors."
    if source_tokens and topic_overlap_ratio < 0.35 and len(overlap_tokens) < 2:
        status = "failed"
        detail = "Rewrite appears to pivot away from the original topic or slug target."
    elif prompt_tokens and not prompt_overlap_tokens:
        status = "failed"
        detail = "Rewrite no longer aligns with the matched prompt family named in the recommendation artifact."
    elif source_entities and len(missing_entities) == len(_dedupe_preserve(source_entities)):
        status = "failed"
        detail = "Rewrite drops the source article's core entity set instead of preserving it."

    return {
        "status": status,
        "detail": detail,
        "source_title": source_title,
        "rewritten_title": rewritten_title,
        "source_topic_tokens": source_tokens,
        "rewritten_topic_tokens": rewritten_tokens,
        "overlap_tokens": overlap_tokens,
        "topic_overlap_ratio": round(topic_overlap_ratio, 3),
        "prompt_overlap_tokens": prompt_overlap_tokens,
        "missing_entities": missing_entities,
    }


def _requirements_for(intent: str, recommendations: dict[str, Any], evidence: dict[str, Any]) -> dict[str, Any]:
    requirements = dict(INTENT_REQUIREMENTS.get(intent, INTENT_REQUIREMENTS["category"]))
    evidence_requirements = evidence.get("evidence_requirements")
    if isinstance(evidence_requirements, dict):
        requirements.update({
            "minimum_total_sources": int(evidence_requirements.get("minimum_total_sources", requirements["minimum_total_sources"])),
            "minimum_external_sources": int(evidence_requirements.get("minimum_external_sources", requirements["minimum_external_sources"])),
            "minimum_internal_sources": int(evidence_requirements.get("minimum_internal_sources", requirements["minimum_internal_sources"])),
        })
    evidence_plan = (
        recommendations.get("evidence_plan")
        or (recommendations.get("blueprint") or {}).get("evidence_plan")
        or {}
    )
    if isinstance(evidence_plan, dict):
        requirements["minimum_total_sources"] = int(evidence_plan.get("required_source_count", requirements["minimum_total_sources"]))
        requirements["minimum_external_sources"] = int(evidence_plan.get("required_external_count", requirements["minimum_external_sources"]))
        requirements["minimum_internal_sources"] = int(evidence_plan.get("required_internal_count", requirements["minimum_internal_sources"]))
        requirements["must_cite_claim_ids"] = [item for item in evidence_plan.get("must_cite_claim_ids", []) if isinstance(item, str)]
    else:
        requirements["must_cite_claim_ids"] = []
    return requirements


def _role_is_security_relevant(role: str) -> bool:
    lowered = role.lower()
    return any(keyword in lowered for keyword in SECURITY_ROLE_KEYWORDS)


def _role_is_reviewer_relevant(role: str) -> bool:
    lowered = role.lower()
    return any(keyword in lowered for keyword in REVIEWER_ROLE_KEYWORDS | SECURITY_ROLE_KEYWORDS)


@dataclass
class HTMLSnapshot:
    visible_text: str
    headings: list[dict[str, Any]]
    dt_questions: list[dict[str, Any]]
    links: list[dict[str, str]]
    paragraphs: list[str]
    table_count: int
    ordered_lists: int
    unordered_lists: int
    jsonld: list[Any]
    title: str

    @property
    def faq_questions(self) -> list[str]:
        faq_index = next((index for index, item in enumerate(self.headings) if "faq" in item["text"].lower()), -1)
        candidates = list(self.dt_questions)
        if faq_index != -1:
            for item in self.headings[faq_index + 1:]:
                if item["level"] <= self.headings[faq_index]["level"]:
                    break
                if _looks_like_faq_question(item["text"]):
                    candidates.append(item)
        ordered = sorted(candidates, key=lambda item: int(item.get("order", 0)))
        return _dedupe_preserve([item["text"] for item in ordered])


class _HTMLSnapshotParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.text_chunks: list[str] = []
        self.headings: list[dict[str, Any]] = []
        self.links: list[dict[str, str]] = []
        self.paragraphs: list[str] = []
        self.jsonld_chunks: list[str] = []
        self.dt_questions: list[dict[str, Any]] = []
        self.table_count = 0
        self.ordered_lists = 0
        self.unordered_lists = 0
        self._node_order = 0
        self._heading_tag: str | None = None
        self._heading_text: list[str] = []
        self._dl_depth = 0
        self._dt_open = False
        self._dt_text: list[str] = []
        self._paragraph_open = False
        self._paragraph_text: list[str] = []
        self._link_href = ""
        self._link_text: list[str] = []
        self._script_ldjson = False
        self._script_text: list[str] = []
        self.title = ""
        self._in_title = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        attrs_dict = dict(attrs)
        if tag in {"h1", "h2", "h3"}:
            self._heading_tag = tag
            self._heading_text = []
        elif tag == "dl":
            self._dl_depth += 1
        elif tag == "dt" and self._dl_depth > 0:
            self._dt_open = True
            self._dt_text = []
        elif tag == "p":
            self._paragraph_open = True
            self._paragraph_text = []
        elif tag == "a":
            self._link_href = attrs_dict.get("href") or ""
            self._link_text = []
        elif tag == "script" and (attrs_dict.get("type") or "").lower() == "application/ld+json":
            self._script_ldjson = True
            self._script_text = []
        elif tag == "table":
            self.table_count += 1
        elif tag == "ol":
            self.ordered_lists += 1
        elif tag == "ul":
            self.unordered_lists += 1
        elif tag == "title":
            self._in_title = True

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag == self._heading_tag and self._heading_tag:
            text = _normalize_text("".join(self._heading_text))
            if text:
                self._node_order += 1
                self.headings.append({"level": int(self._heading_tag[1]), "text": text, "order": self._node_order})
            self._heading_tag = None
            self._heading_text = []
        elif tag == "dt" and self._dt_open:
            text = _normalize_text("".join(self._dt_text))
            if _looks_like_faq_question(text):
                self._node_order += 1
                self.dt_questions.append({"text": text, "order": self._node_order})
            self._dt_open = False
            self._dt_text = []
        elif tag == "dl" and self._dl_depth > 0:
            self._dl_depth -= 1
        elif tag == "p" and self._paragraph_open:
            text = _normalize_text("".join(self._paragraph_text))
            if text:
                self.paragraphs.append(text)
            self._paragraph_open = False
            self._paragraph_text = []
        elif tag == "a" and self._link_href:
            text = _normalize_text("".join(self._link_text))
            self.links.append({"href": self._link_href, "text": text})
            self._link_href = ""
            self._link_text = []
        elif tag == "script" and self._script_ldjson:
            payload = "".join(self._script_text).strip()
            if payload:
                self.jsonld_chunks.append(payload)
            self._script_ldjson = False
            self._script_text = []
        elif tag == "title":
            self._in_title = False

    def handle_data(self, data: str) -> None:
        if not data:
            return
        if self._script_ldjson:
            self._script_text.append(data)
            return
        self.text_chunks.append(data)
        if self._heading_tag:
            self._heading_text.append(data)
        if self._dt_open:
            self._dt_text.append(data)
        if self._paragraph_open:
            self._paragraph_text.append(data)
        if self._link_href:
            self._link_text.append(data)
        if self._in_title:
            self.title += data


def _parse_html_snapshot(html_text: str) -> HTMLSnapshot:
    parser = _HTMLSnapshotParser()
    parser.feed(html_text)
    jsonld: list[Any] = []
    for snippet in parser.jsonld_chunks:
        try:
            jsonld.append(json.loads(snippet))
        except json.JSONDecodeError:
            continue
    return HTMLSnapshot(
        visible_text=_normalize_text(" ".join(parser.text_chunks)),
        headings=parser.headings,
        dt_questions=parser.dt_questions,
        links=parser.links,
        paragraphs=parser.paragraphs,
        table_count=parser.table_count,
        ordered_lists=parser.ordered_lists,
        unordered_lists=parser.unordered_lists,
        jsonld=jsonld,
        title=_normalize_text(parser.title),
    )


def _schema_summary(schema_data: Any) -> dict[str, Any]:
    nodes = _walk_nodes(schema_data)
    blogposting = next((node for node in nodes if _has_type(node, "BlogPosting")), None)
    person = next((node for node in nodes if _has_type(node, "Person") and node.get("name")), None)
    organization = next((node for node in nodes if _has_type(node, "Organization") and node.get("name")), None)
    questions = [str(node.get("name", "")).strip() for node in nodes if _has_type(node, "Question") and node.get("name")]
    return {
        "types": sorted(_type_names(schema_data)),
        "author_name": str((person or {}).get("name", "")).strip(),
        "author_role": str((person or {}).get("jobTitle", "")).strip(),
        "organization_name": str((organization or {}).get("name", "")).strip(),
        "faq_questions": questions,
        "headline": str((blogposting or {}).get("headline", "")).strip(),
    }


def _source_mix(sources: list[dict[str, Any]], article_url: str) -> tuple[int, int, list[str], list[str]]:
    article_host = urlparse(article_url).hostname or ""
    internal: list[str] = []
    external: list[str] = []
    for source in sources:
        raw_url = _canonicalize_url(str(source.get("url", "")))
        if not raw_url:
            continue
        source_type = str(source.get("source_type", "")).lower()
        source_host = urlparse(raw_url).hostname or ""
        if "internal" in source_type or source_host == article_host:
            internal.append(raw_url)
        else:
            external.append(raw_url)
    internal = _dedupe_preserve(internal)
    external = _dedupe_preserve(external)
    return len(internal), len(external), internal, external


def _count_internal_links(snapshot: HTMLSnapshot, article_url: str) -> tuple[int, list[str]]:
    article_host = urlparse(article_url).hostname or ""
    article_canonical = _canonicalize_url(article_url)
    internal: list[str] = []
    for link in snapshot.links:
        href = _canonicalize_url(link["href"], article_url)
        if not href:
            continue
        if urlparse(href).hostname != article_host:
            continue
        if href == article_canonical:
            continue
        internal.append(href)
    unique = _dedupe_preserve(internal)
    return len(unique), unique


def _validate_rec_implementation(manifest: dict, recommendations: dict) -> list[str]:
    issues: list[str] = []
    if not isinstance(manifest, dict):
        manifest = {}
    if not isinstance(recommendations, dict):
        recommendations = {}
    rec_map = manifest.get("rec_implementation_map")
    if not isinstance(rec_map, dict):
        rec_map = {}
    recs = recommendations.get("recommendations")
    if not isinstance(recs, list):
        return issues

    for rec in recs:
        if not isinstance(rec, dict):
            continue
        if rec.get("priority") != "critical" or rec.get("source") != "llm":
            continue
        rec_id = str(rec.get("id") or "").strip()
        if not rec_id:
            issues.append("critical LLM recommendation has no valid implementation entry")
            continue
        entry = rec_map.get(rec_id)
        if not isinstance(entry, dict):
            issues.append(f"{rec_id} has no valid implementation entry")
            continue
        implemented = entry.get("implemented")
        if implemented is True:
            schema_fields = entry.get("schema_fields")
            evidence_inserted = entry.get("evidence_inserted")
            has_schema_fields = isinstance(schema_fields, list) and bool(schema_fields)
            has_evidence = isinstance(evidence_inserted, list) and bool(evidence_inserted)
            if not str(entry.get("section") or "").strip() or not str(entry.get("anchor") or "").strip() or not (has_schema_fields or has_evidence):
                issues.append(f"{rec_id} has no valid implementation entry")
            continue
        if implemented is False:
            reason = str(entry.get("reason") or "").strip()
            if reason in {"non-applicable", "data_missing"}:
                continue
            if reason.startswith("superseded_by_") and len(reason) > len("superseded_by_"):
                continue
            issues.append(f"{rec_id} has no valid implementation entry")
            continue
        issues.append(f"{rec_id} has no valid implementation entry")
    return issues


def _inline_evidence_usage(snapshot: HTMLSnapshot, evidence: dict[str, Any], article_url: str) -> tuple[int, set[str], list[str]]:
    visible = snapshot.visible_text.lower()
    linked_urls = {
        _canonicalize_url(item["href"], article_url)
        for item in snapshot.links
        if _canonicalize_url(item["href"], article_url)
    }
    matched_claim_ids: set[str] = set()
    referenced_items: list[str] = []

    for source in evidence.get("sources", []):
        if not isinstance(source, dict):
            continue
        source_url = _canonicalize_url(str(source.get("url", "")))
        source_label = _normalize_text(str(source.get("title", "") or source.get("source_label", ""))).lower()
        if source_url and source_url in linked_urls:
            referenced_items.append(source_url)
        elif source_label and source_label in visible:
            referenced_items.append(source_url or source_label)

    for claim in evidence.get("claims", []):
        if not isinstance(claim, dict):
            continue
        claim_id = str(claim.get("id", "")).strip()
        source_url = _canonicalize_url(str(claim.get("source_url", "")))
        source_label = _normalize_text(str(claim.get("source_label", ""))).lower()
        claim_text = _normalize_text(str(claim.get("claim", ""))).lower()
        if source_url and source_url in linked_urls:
            if claim_id:
                matched_claim_ids.add(claim_id)
            referenced_items.append(source_url)
        elif source_label and source_label in visible:
            if claim_id:
                matched_claim_ids.add(claim_id)
            referenced_items.append(source_url or source_label)
        elif claim_text and claim_text[:90] in visible:
            if claim_id:
                matched_claim_ids.add(claim_id)
            referenced_items.append(claim_id or claim_text[:90])

    unique_refs = _dedupe_preserve(referenced_items)
    return len(unique_refs), matched_claim_ids, unique_refs


def _reviewer_plan(recommendations: dict[str, Any]) -> dict[str, Any]:
    plan = recommendations.get("reviewer_plan") or (recommendations.get("blueprint") or {}).get("reviewer_plan")
    if isinstance(plan, dict):
        return plan
    author_plan = (recommendations.get("blueprint") or {}).get("author_plan") or {}
    if not isinstance(author_plan, dict):
        return {}
    return {
        "status": "selected" if author_plan.get("status") not in {"missing", "risky"} else "missing",
        "display_name": author_plan.get("display_name"),
        "display_role": author_plan.get("role"),
    }


def _validate_author(
    article: dict[str, Any],
    recommendations: dict[str, Any],
    reviewers: list[dict[str, Any]],
    snapshot: HTMLSnapshot,
    schema: dict[str, Any],
    intent: str,
) -> dict[str, Any]:
    review_plan = _reviewer_plan(recommendations)
    review_lookup = {str(item.get("id")): item for item in reviewers if isinstance(item, dict)}
    source_author = str(((article.get("trust") or {}).get("author") or {}).get("name", "")).strip()
    source_role = str(((article.get("trust") or {}).get("author") or {}).get("role", "")).strip()
    source_reviewer_id = ((article.get("trust") or {}).get("reviewer_id"))
    schema_author_name = schema.get("author_name", "")
    schema_author_role = schema.get("author_role", "")
    reviewer_id = review_plan.get("reviewer_id") or source_reviewer_id
    selected_reviewer = review_lookup.get(str(reviewer_id)) if reviewer_id else None
    reviewer_name = str((selected_reviewer or {}).get("name") or (selected_reviewer or {}).get("display_name") or (selected_reviewer or {}).get("full_name") or "").strip()
    reviewer_role = str((selected_reviewer or {}).get("role") or "").strip()
    display_name = str(review_plan.get("display_name") or reviewer_name or schema_author_name or source_author or "").strip()
    display_role = str(review_plan.get("display_role") or reviewer_role or schema_author_role or source_role or "").strip()
    visible = snapshot.visible_text.lower()
    uses_article_author = bool(source_author) and display_name.lower() == source_author.lower()
    author_fallback_available = not reviewers and not reviewer_id and uses_article_author
    full_name_author_fallback = author_fallback_available and _has_first_and_last_name(source_author)
    single_name_with_role = author_fallback_available and _is_single_name_with_role(source_author, source_role)

    result = {
        "status": "passed",
        "display_name": display_name,
        "display_role": display_role,
        "reviewer_id": reviewer_id,
        "detail": "",
    }
    if _is_weak_byline(display_name) and not single_name_with_role:
        result["status"] = "failed"
        result["detail"] = "Visible byline is anonymous, team-based, or missing a full name."
        return result
    if display_name.lower() not in visible:
        result["status"] = "failed"
        result["detail"] = "Rendered HTML does not expose the selected reviewer or author name visibly."
        return result
    if display_role and display_role.lower() not in visible:
        result["status"] = "failed"
        result["detail"] = "Rendered trust block is missing a visible reviewer role or credential."
        return result
    if not display_role and not full_name_author_fallback:
        result["status"] = "failed"
        result["detail"] = "Rendered trust block is missing a visible reviewer role or credential."
        return result
    if reviewer_id:
        reviewer = review_lookup.get(str(reviewer_id))
        if not reviewer or not reviewer.get("active", False):
            result["status"] = "failed"
            result["detail"] = "Selected reviewer is not present as an active site reviewer."
            return result
        review_areas = {str(item).lower() for item in reviewer.get("review_areas", [])}
        article_types = {str(item).lower() for item in reviewer.get("default_for_article_types", [])}
        article_type = str(recommendations.get("article_type", "")).lower()
        if intent == "security":
            if "security" not in review_areas or not _role_is_security_relevant(str(reviewer.get("role", ""))):
                result["status"] = "failed"
                result["detail"] = "No publicly valid security/compliance reviewer is available for this article."
                return result
        elif intent not in review_areas and article_type and article_type not in article_types:
            result["status"] = "failed"
            result["detail"] = "Selected reviewer does not match the article's review area."
            return result
    elif intent == "security":
        result["status"] = "failed"
        result["detail"] = "Security page needs a public security/compliance/legal reviewer, and none was selected."
        return result
    elif single_name_with_role:
        result["detail"] = f"{display_name} is accepted via single-name-with-role author validation because trust.author.role is {source_role}."
        return result
    elif full_name_author_fallback:
        result["detail"] = f"{display_name} is accepted from the article author fallback because site reviewers.json is empty."
        return result
    elif not _role_is_reviewer_relevant(display_role):
        result["status"] = "failed"
        result["detail"] = "Author role is too weak to act as a reviewer-backed trust signal."
        return result

    result["detail"] = f"{display_name} is a visible full-name reviewer with a rendered role line."
    return result


def _validate_trust_block(author_validation: dict[str, Any], reviewers: list[dict[str, Any]]) -> dict[str, Any]:
    review_lookup = {
        str(item.get("id")): item
        for item in reviewers
        if isinstance(item, dict) and item.get("id")
    }
    reviewer_id = author_validation.get("reviewer_id")
    author_passed = author_validation.get("status") == "passed"

    if reviewer_id:
        reviewer = review_lookup.get(str(reviewer_id))
        reviewer_name = str(
            (reviewer or {}).get("name")
            or (reviewer or {}).get("display_name")
            or (reviewer or {}).get("full_name")
            or ""
        ).strip()
        if author_passed and reviewer and reviewer.get("active", False) and reviewer_name:
            return {
                "passed": True,
                "source": "reviewers_json",
                "author_name": reviewer_name,
            }
        return {
            "passed": False,
            "source": "reviewers_json",
            "author_name": "",
        }

    display_name = str(author_validation.get("display_name") or "").strip()
    if author_passed and display_name:
        return {
            "passed": True,
            "source": "author_validation",
            "author_name": display_name,
        }
    return {
        "passed": False,
        "source": "author_validation",
        "author_name": "",
    }


def _numeric_score_breakdown(
    module_status: dict[str, bool],
    required_modules: list[str],
    author_validation: dict[str, Any],
    scope_drift: dict[str, Any],
    schema_status: str,
    inline_evidence_passed: bool,
    rec_implementation_issues: list[str],
) -> dict[str, Any]:
    required_total = len(required_modules)
    required_passed = sum(1 for item in required_modules if module_status.get(item, False))
    required_points = round(16 * (required_passed / required_total)) if required_total else 0
    checks = {
        "required_modules": {
            "points": required_points,
            "max": 16,
            "passed": required_passed,
            "total": required_total,
        },
        "trust_author": {
            "points": 6 if author_validation.get("status") == "passed" else 0,
            "max": 6,
            "passed": author_validation.get("status") == "passed",
        },
        "evidence": {
            "points": 6 if inline_evidence_passed else 0,
            "max": 6,
            "passed": inline_evidence_passed,
        },
        "schema": {
            "points": 6 if schema_status == "passed" else 0,
            "max": 6,
            "passed": schema_status == "passed",
        },
        "scope": {
            "points": 4 if scope_drift.get("status") == "passed" else 0,
            "max": 4,
            "passed": scope_drift.get("status") == "passed",
        },
        "rec_implementation": {
            "points": 2 if not rec_implementation_issues else 0,
            "max": 2,
            "passed": not rec_implementation_issues,
        },
    }
    total = sum(int(item["points"]) for item in checks.values())
    return {
        "score": max(0, min(40, total)),
        "score_max": 40,
        "checks": checks,
    }


def build_article_manifest(run_dir: Path, article_slug: str, audit_after: int | None = None) -> dict[str, Any]:
    state_path = run_dir / "state.json"
    state = _require_mapping(_load_required_json(state_path, "state"), "state", state_path)
    outputs = run_dir / "outputs"
    article_path = outputs / "articles" / f"{article_slug}.json"
    article = _require_mapping(_load_required_json(article_path, "article artifact"), "article artifact", article_path)
    recommendations_path = outputs / "recommendations" / f"{article_slug}.json"
    recommendations = _require_mapping(_load_required_json(recommendations_path, "recommendation artifact"), "recommendation artifact", recommendations_path)
    evidence_path = outputs / "evidence" / f"{article_slug}.json"
    evidence = _load_json(evidence_path) if evidence_path.exists() else {}
    if not isinstance(evidence, dict):
        evidence = {}
    html_path = outputs / "optimised" / f"{article_slug}.html"
    schema_path = outputs / "optimised" / f"{article_slug}.schema.json"
    html_text = _read_required_text(html_path, "rendered HTML")
    schema_payload = _load_required_json(schema_path, "schema package")
    existing_manifest_path = outputs / "optimised" / f"{article_slug}.manifest.json"
    existing_manifest = _load_json(existing_manifest_path) if existing_manifest_path.exists() else {}
    if not isinstance(existing_manifest, dict):
        existing_manifest = {}
    site_dir = Path((state.get("outputs") or {}).get("site_dir", run_dir.parent.parent / "sites" / state.get("site_key", "")))
    reviewers_path = site_dir / "reviewers.json"
    reviewers = _load_json(reviewers_path) if reviewers_path.exists() else []
    if not isinstance(reviewers, list):
        reviewers = []

    snapshot = _parse_html_snapshot(html_text)
    file_schema = _schema_summary(schema_payload)
    html_schema_types = sorted(_type_names(snapshot.jsonld))
    article_url = str(article.get("url", ""))
    intent = _infer_intent(article, recommendations, evidence)
    requirements = _requirements_for(intent, recommendations, evidence)
    internal_source_count, external_source_count, internal_sources, external_sources = _source_mix(
        [item for item in evidence.get("sources", []) if isinstance(item, dict)],
        article_url,
    )
    inline_evidence_count, matched_claim_ids, referenced_items = _inline_evidence_usage(snapshot, evidence, article_url)
    internal_link_count, internal_links = _count_internal_links(snapshot, article_url)
    author_validation = _validate_author(article, recommendations, reviewers if isinstance(reviewers, list) else [], snapshot, file_schema, intent)
    trust_block = _validate_trust_block(author_validation, reviewers if isinstance(reviewers, list) else [])
    scope_drift = _scope_drift_check(article, recommendations, snapshot)

    required_primary = (
        ((recommendations.get("blueprint") or {}).get("schema_plan") or {}).get("primary_type")
        or "BlogPosting"
    )
    visible_faq_questions = snapshot.faq_questions
    schema_faq_questions = [item for item in file_schema["faq_questions"] if item]
    faq_schema_passes = True
    faq_reason = ""
    if visible_faq_questions or schema_faq_questions:
        faq_schema_passes = bool(visible_faq_questions) and bool(schema_faq_questions) and len(visible_faq_questions) == len(schema_faq_questions)
        if faq_schema_passes:
            faq_schema_passes = all(question in schema_faq_questions for question in visible_faq_questions)
        if not faq_schema_passes:
            faq_reason = "Visible FAQ questions do not match FAQPage schema."

    need_person = author_validation["status"] == "passed" or bool(_reviewer_plan(recommendations).get("display_name"))
    required_types = {required_primary, "BreadcrumbList", "Organization"}
    if visible_faq_questions:
        required_types.add("FAQPage")
    if need_person:
        required_types.add("Person")
    file_types = set(file_schema["types"])
    html_types = set(html_schema_types)
    missing_schema_types = sorted(item for item in required_types if item not in file_types)
    missing_html_types = sorted(item for item in required_types if item not in html_types)
    schema_notes: list[str] = []
    if file_schema["headline"] and snapshot.headings:
        visible_h1 = next((item["text"] for item in snapshot.headings if item["level"] == 1), "")
        if visible_h1 and file_schema["headline"] != visible_h1:
            schema_notes.append("BlogPosting headline does not match the visible H1.")
    if author_validation["status"] == "passed" and file_schema.get("author_name") != author_validation.get("display_name"):
        schema_notes.append("Schema Person author does not match the visible reviewer block.")
    if faq_reason:
        schema_notes.append(faq_reason)
    schema_status = "passed"
    if missing_schema_types or missing_html_types or schema_notes:
        schema_status = "failed"
    verified_from_html = not missing_html_types

    title_text = snapshot.title or next((item["text"] for item in snapshot.headings if item["level"] == 1), "")
    question_heading_count = sum(1 for item in snapshot.headings if item["level"] in {2, 3} and item["text"].endswith("?"))
    average_paragraph_words = sum(len(paragraph.split()) for paragraph in snapshot.paragraphs) / max(len(snapshot.paragraphs), 1)
    short_paragraph_ratio = (
        sum(len(paragraph.split()) <= 80 for paragraph in snapshot.paragraphs) / max(len(snapshot.paragraphs), 1)
        if snapshot.paragraphs else 0.0
    )
    host = (urlparse(article_url).hostname or "").lower()
    brand_name = host[4:] if host.startswith("www.") else host
    brand_name = brand_name.split(".")[0]
    inline_evidence_passed = (
        inline_evidence_count >= requirements["minimum_inline_references"]
        and internal_source_count >= requirements["minimum_internal_sources"]
        and external_source_count >= requirements["minimum_external_sources"]
        and (internal_source_count + external_source_count) >= requirements["minimum_total_sources"]
        and all(item in matched_claim_ids for item in requirements.get("must_cite_claim_ids", []))
    )

    module_status = {
        "tldr_block": "tl;dr" in snapshot.visible_text.lower(),
        "trust_block": author_validation["status"] == "passed" and any(date_value in snapshot.visible_text for date_value in [
            str(((article.get("trust") or {}).get("published_at")) or ""),
            str(((article.get("trust") or {}).get("updated_at")) or ""),
        ]),
        "question_headings": question_heading_count >= 2,
        "atomic_paragraphs": short_paragraph_ratio >= 0.6 and average_paragraph_words <= 75,
        "inline_evidence": inline_evidence_passed,
        "semantic_html": len([item for item in snapshot.headings if item["level"] == 2]) >= 2 and (snapshot.table_count or snapshot.unordered_lists or snapshot.ordered_lists),
        "chunk_complete_sections": len([item for item in snapshot.headings if item["level"] == 2]) >= 3 and len(snapshot.paragraphs) >= 5,
        "differentiation": brand_name in snapshot.visible_text.lower() and len(referenced_items) >= 2,
        "faq_block": len(visible_faq_questions) >= 3,
        "faq_schema": faq_schema_passes,
        "table_block": snapshot.table_count >= 1,
        "howto_steps": snapshot.ordered_lists >= 1,
        "howto_schema": "HowTo" in file_types,
        "comparison_table": snapshot.table_count >= 1,
        "toc_jump_links": any((link.get("href") or "").startswith("#") for link in snapshot.links),
        "year_modifier": bool(re.search(r"\b20\d{2}\b", title_text)),
        "specialized_schema": schema_status == "passed",
    }

    required_modules: list[str] = []
    quality_contract = recommendations.get("quality_contract")
    if isinstance(quality_contract, dict):
        for bucket in ("universal", "conditional"):
            for item in quality_contract.get(bucket, []):
                if not isinstance(item, dict):
                    continue
                if item.get("required") and item.get("applicable", True):
                    key = str(item.get("key", "")).strip()
                    if key:
                        required_modules.append(key)
    if not required_modules:
        required_modules = ["tldr_block", "trust_block", "question_headings", "atomic_paragraphs", "inline_evidence", "semantic_html", "chunk_complete_sections", "differentiation", "specialized_schema"]
        if visible_faq_questions:
            required_modules.extend(["faq_block", "faq_schema"])
    required_modules = _dedupe_preserve(required_modules)
    missing_required_modules = [item for item in required_modules if not module_status.get(item, False)]

    blocking_issues: list[str] = []
    if author_validation["status"] != "passed":
        blocking_issues.append(author_validation["detail"])
    if scope_drift["status"] != "passed":
        blocking_issues.append(scope_drift["detail"])
    if internal_source_count + external_source_count < requirements["minimum_total_sources"]:
        blocking_issues.append(f"Evidence pack has {internal_source_count + external_source_count} total sources; requires {requirements['minimum_total_sources']}.")
    if internal_source_count < requirements["minimum_internal_sources"]:
        blocking_issues.append(f"Evidence pack has {internal_source_count} internal sources; requires {requirements['minimum_internal_sources']}.")
    if external_source_count < requirements["minimum_external_sources"]:
        blocking_issues.append(f"Evidence pack has {external_source_count} external sources; requires {requirements['minimum_external_sources']}.")
    if inline_evidence_count < requirements["minimum_inline_references"]:
        blocking_issues.append(f"Rendered article has {inline_evidence_count} inline evidence references; requires {requirements['minimum_inline_references']}.")
    missing_claim_ids = [item for item in requirements.get("must_cite_claim_ids", []) if item not in matched_claim_ids]
    if missing_claim_ids:
        blocking_issues.append(f"Rendered article is missing required cited claims: {', '.join(missing_claim_ids)}.")
    link_plan = (
        recommendations.get("internal_link_plan")
        or (recommendations.get("blueprint") or {}).get("internal_link_plan")
        or {}
    )
    minimum_internal_links = int(link_plan.get("minimum_internal_links", 3))
    if internal_link_count < minimum_internal_links:
        blocking_issues.append(f"Rendered article has {internal_link_count} internal links; requires {minimum_internal_links}.")
    if schema_status != "passed":
        if missing_schema_types:
            blocking_issues.append(f"Schema file is missing required types: {', '.join(missing_schema_types)}.")
        if missing_html_types:
            blocking_issues.append(f"Rendered HTML is missing required schema types: {', '.join(missing_html_types)}.")
        blocking_issues.extend(schema_notes)
    rec_implementation_issues = _validate_rec_implementation(existing_manifest, recommendations)
    blocking_issues.extend(rec_implementation_issues)

    quality_status = "passed" if not blocking_issues and not missing_required_modules else "failed"
    passed_modules = sorted(key for key, value in module_status.items() if value)
    failed_modules = sorted(key for key, value in module_status.items() if not value)
    passed_required_modules = sorted(item for item in required_modules if module_status.get(item, False))
    failed_required_modules = sorted(item for item in required_modules if not module_status.get(item, False))
    module_checks = {
        "passed_count": len(passed_required_modules),
        "failed_count": len(failed_required_modules),
        "passed": passed_required_modules,
        "failed": failed_required_modules,
        "all_passed": passed_modules,
        "all_failed": failed_modules,
    }
    score_breakdown = _numeric_score_breakdown(
        module_status,
        required_modules,
        author_validation,
        scope_drift,
        schema_status,
        inline_evidence_passed,
        rec_implementation_issues,
    )
    audit = recommendations.get("audit") or {}
    article_stage = next((item for item in state.get("articles", []) if item.get("slug") == article_slug), {})
    stage_draft = ((article_stage.get("stages") or {}).get("draft") or {})
    audit_before = _coerce_audit_score(audit.get("score_before"))
    resolved_audit_after = _first_audit_score(
        audit_after,
        existing_manifest.get("audit_after"),
        stage_draft.get("audit_after"),
        score_breakdown["score"],
    )

    return {
        "article_slug": article_slug,
        "geo_contract_version": recommendations.get("geo_contract_version", "v1"),
        "article_type": recommendations.get("article_type"),
        "intent_class": intent,
        "audit_before": audit_before,
        "audit_after": resolved_audit_after,
        "score_breakdown": score_breakdown,
        "module_checks": module_checks,
        "quality_gate": {
            "status": quality_status,
            "passed": quality_status == "passed",
            "missing_required_modules": missing_required_modules,
            "blocking_issues": blocking_issues,
        },
        "rec_implementation_map": existing_manifest.get("rec_implementation_map") if isinstance(existing_manifest.get("rec_implementation_map"), dict) else {},
        "implemented_modules": sorted(key for key, value in module_status.items() if value),
        "missing_required_modules": missing_required_modules,
        "author_validation": author_validation,
        "trust_block": trust_block,
        "scope_drift": scope_drift,
        "inline_evidence_count": inline_evidence_count,
        "internal_source_count": internal_source_count,
        "external_source_count": external_source_count,
        "internal_link_count": internal_link_count,
        "evidence_requirements": requirements,
        "schema_checks": {
            "status": schema_status,
            "verified_from_html": verified_from_html,
            "file_types": sorted(file_types),
            "html_types": sorted(html_types),
            "missing_from_file": missing_schema_types,
            "missing_from_html": missing_html_types,
            "faq_questions_visible": visible_faq_questions,
            "faq_questions_schema": schema_faq_questions,
            "notes": schema_notes,
        },
        "evidence_sources_used": referenced_items,
        "internal_links": internal_links,
        "reader": {
            "title": article.get("title") or article_slug,
            "open_url": f"/api/runs/{run_dir.name}/optimised/{article_slug}.html",
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate one optimised article deterministically.")
    parser.add_argument("run_dir", type=Path)
    parser.add_argument("article_slug")
    parser.add_argument("--audit-after", type=int, default=None)
    args = parser.parse_args(argv)
    manifest = build_article_manifest(args.run_dir.resolve(), args.article_slug, audit_after=args.audit_after)
    output_path = args.run_dir.resolve() / "outputs" / "optimised" / f"{args.article_slug}.manifest.json"
    output_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({
        "article_slug": args.article_slug,
        "status": manifest["quality_gate"]["status"],
        "missing_required_modules": manifest["missing_required_modules"],
    }, indent=2))
    return 0 if manifest["quality_gate"]["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
