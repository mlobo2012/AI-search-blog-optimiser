#!/usr/bin/env python3
"""Deterministic GEO hygiene linter for captured article artifacts."""

from __future__ import annotations

import re
from html.parser import HTMLParser
from typing import Any


FAQ_APPLICABLE_PRESETS = {"announcement_update", "pillar"}
WEAK_BYLINES = {"", "admin", "anonymous", "author", "blog", "editor", "editorial", "marketing", "staff", "team"}
VALID_SCHEMA_TYPES = {
    "BreadcrumbList",
    "FAQPage",
    "Organization",
    "Person",
}


class _JsonLdParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.has_jsonld = False
        self._in_jsonld = False
        self._text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_dict = {name.lower(): value for name, value in attrs}
        if tag.lower() == "script" and (attrs_dict.get("type") or "").lower() == "application/ld+json":
            self._in_jsonld = True
            self._text = []

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "script" and self._in_jsonld:
            if "".join(self._text).strip():
                self.has_jsonld = True
            self._in_jsonld = False
            self._text = []

    def handle_data(self, data: str) -> None:
        if self._in_jsonld:
            self._text.append(data)


def lint_article(article: dict, evidence: dict, voice_meta: dict) -> list[dict]:
    """Return deterministic GEO hygiene recommendations for one captured article."""
    if not isinstance(article, dict):
        article = {}
    if not isinstance(evidence, dict):
        evidence = {}
    if not isinstance(voice_meta, dict):
        voice_meta = {}

    items: list[dict] = []

    def add(
        item_id: str,
        dimension: str,
        severity: str,
        evidence_value: str,
        auto_fix: dict[str, Any] | None = None,
    ) -> None:
        items.append({
            "id": item_id,
            "source": "rubric",
            "category": "geo_hygiene",
            "dimension": dimension,
            "severity": severity,
            "priority": severity,
            "signal_types": ["rubric"],
            "evidence": [evidence_value],
            "auto_fix": auto_fix,
            "title": dimension.replace("_", " ").capitalize(),
            "description": evidence_value,
            "fix": _fix_text(item_id),
        })

    meta = _as_dict(article.get("meta"))
    if not _text(meta.get("description")):
        add(
            "meta_description_empty",
            "metadata",
            "high",
            "article.meta.description is empty",
            {"field": "meta.description", "operation": "generate_from_summary"},
        )

    missing_og = [field for field in ("title", "description", "image") if not _meta_value(meta, "og", field)]
    if missing_og:
        add(
            "og_tags_incomplete",
            "metadata",
            "medium",
            "missing Open Graph fields: " + ", ".join(f"og:{field}" for field in missing_og),
            {"fields": [f"og:{field}" for field in missing_og], "operation": "copy_from_article_metadata"},
        )

    missing_twitter = [field for field in ("card", "title", "description") if not _meta_value(meta, "twitter", field)]
    if missing_twitter:
        add(
            "twitter_card_incomplete",
            "metadata",
            "medium",
            "missing Twitter card fields: " + ", ".join(f"twitter:{field}" for field in missing_twitter),
            {"fields": [f"twitter:{field}" for field in missing_twitter], "operation": "copy_from_article_metadata"},
        )

    schema_types = _schema_types(article)
    if not _has_jsonld(article):
        add(
            "jsonld_missing",
            "schema",
            "critical",
            "no JSON-LD detected in article schema or HTML",
            {"field": "schema.raw_ldjson", "operation": "add_blogposting_jsonld"},
        )

    preset = _preset(article, evidence, voice_meta)
    if _faq_applicable(article, preset) and "FAQPage" not in schema_types:
        add(
            "faq_schema_missing",
            "schema",
            "critical",
            f"FAQPage schema missing for preset {preset or 'unknown'}",
            {"schema_type": "FAQPage", "operation": "add_matching_faqpage_schema"},
        )

    if "BreadcrumbList" not in schema_types:
        add(
            "breadcrumb_schema_missing",
            "schema",
            "high",
            "BreadcrumbList schema missing",
            {"schema_type": "BreadcrumbList", "operation": "add_breadcrumb_schema"},
        )

    author_name = _author_name(article)
    if _has_full_name(author_name) and "Person" not in schema_types:
        add(
            "person_schema_missing",
            "schema",
            "high",
            f"Person schema missing for author: {author_name}",
            {"schema_type": "Person", "operation": "add_author_person_schema"},
        )

    if "Organization" not in schema_types:
        add(
            "organization_schema_missing",
            "schema",
            "high",
            "Organization schema missing",
            {"schema_type": "Organization", "operation": "add_organization_schema"},
        )

    cta_text, cta_has_link = _cta(article)
    if not cta_text or (_generic_cta(cta_text) and not cta_has_link):
        evidence_text = "CTA missing" if not cta_text else f"generic CTA without link: {cta_text}"
        add("cta_missing_or_generic", "conversion", "medium", evidence_text, None)

    if _weak_byline(author_name) and not _has_reviewer_fallback(evidence, voice_meta):
        add("byline_weak", "trust", "critical", f"weak byline: {author_name or 'missing'}", None)

    if not _updated_at(article, schema_types):
        add(
            "updated_at_missing",
            "trust",
            "medium",
            "dateModified / updated_at missing",
            {"field": "trust.updated_at", "operation": "set_reviewed_or_modified_date"},
        )

    internal_links = _internal_links(article)
    if len(internal_links) < 2:
        add(
            "internal_links_below_min",
            "internal_links",
            "medium",
            f"article.links.internal has {len(internal_links)} entries; requires 2",
            None,
        )

    inbound_links = _inbound_internal_links(article)
    if len(inbound_links) == 0:
        add("inbound_internal_links_zero", "internal_links", "medium", "article.links.inbound_internal is empty", None)

    return items


def _fix_text(item_id: str) -> str:
    return {
        "meta_description_empty": "Write a concise meta description grounded in the article summary.",
        "og_tags_incomplete": "Populate og:title, og:description, and og:image from the article metadata.",
        "twitter_card_incomplete": "Populate twitter:card, twitter:title, and twitter:description.",
        "jsonld_missing": "Add BlogPosting JSON-LD to the rendered HTML head.",
        "faq_schema_missing": "Add FAQPage JSON-LD matching the visible FAQ block.",
        "breadcrumb_schema_missing": "Add BreadcrumbList JSON-LD for Home, Blog, and the article.",
        "person_schema_missing": "Add Person JSON-LD for the visible full-name author or reviewer.",
        "organization_schema_missing": "Add Organization JSON-LD for the publishing brand.",
        "cta_missing_or_generic": "Add a specific, linked CTA aligned with the article intent.",
        "byline_weak": "Replace the weak byline with a full-name author or valid reviewer block.",
        "updated_at_missing": "Add a visible updated date and dateModified schema field.",
        "internal_links_below_min": "Add at least two contextual internal links in the article body.",
        "inbound_internal_links_zero": "Add links to this article from relevant existing site pages.",
    }.get(item_id, "Fix the detected GEO hygiene gap.")


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _text(value: Any) -> str:
    if isinstance(value, list):
        value = " ".join(str(item) for item in value if item)
    return str(value or "").strip()


def _meta_value(meta: dict[str, Any], group: str, field: str) -> str:
    nested = _as_dict(meta.get(group))
    direct = meta.get(f"{group}_{field}") or meta.get(f"{group}:{field}")
    return _text(nested.get(field) or direct)


def _schema_types(article: dict[str, Any]) -> set[str]:
    schema = _as_dict(article.get("schema"))
    values: set[str] = set()
    for key in ("types_present", "types", "type_names"):
        raw = schema.get(key)
        if isinstance(raw, list):
            values.update(str(item).strip() for item in raw if str(item).strip())
    raw_ldjson = schema.get("raw_ldjson")
    values.update(_types_from_node(raw_ldjson))
    for key in ("jsonld", "ld_json", "structured_data"):
        values.update(_types_from_node(article.get(key)))
    return {value for value in values if value in VALID_SCHEMA_TYPES or value}


def _types_from_node(node: Any) -> set[str]:
    found: set[str] = set()
    if isinstance(node, dict):
        value = node.get("@type")
        if isinstance(value, str):
            found.add(value)
        elif isinstance(value, list):
            found.update(str(item) for item in value if item)
        for child in node.values():
            found.update(_types_from_node(child))
    elif isinstance(node, list):
        for child in node:
            found.update(_types_from_node(child))
    return found


def _has_jsonld(article: dict[str, Any]) -> bool:
    schema = _as_dict(article.get("schema"))
    raw = schema.get("raw_ldjson")
    if isinstance(raw, list) and raw:
        return True
    if isinstance(raw, dict) and raw:
        return True
    for key in ("html", "body_html", "raw_html"):
        html = article.get(key)
        if isinstance(html, str) and _html_has_jsonld(html):
            return True
    return bool(_schema_types(article) - {"Article", "BlogPosting", "NewsArticle"})


def _html_has_jsonld(html: str) -> bool:
    parser = _JsonLdParser()
    parser.feed(html)
    return parser.has_jsonld


def _preset(article: dict[str, Any], evidence: dict[str, Any], voice_meta: dict[str, Any]) -> str:
    for source in (article, evidence, voice_meta):
        for key in ("preset", "article_type", "intent_preset"):
            value = _text(source.get(key) if isinstance(source, dict) else "")
            if value:
                return value
    return ""


def _faq_applicable(article: dict[str, Any], preset: str) -> bool:
    structure = _as_dict(article.get("structure"))
    if preset in FAQ_APPLICABLE_PRESETS:
        return True
    return bool(structure.get("faq_blocks_detected"))


def _author_name(article: dict[str, Any]) -> str:
    trust = _as_dict(article.get("trust"))
    author = _as_dict(trust.get("author"))
    return _text(author.get("name") or trust.get("author_name") or article.get("author"))


def _name_tokens(name: str) -> list[str]:
    return re.findall(r"[A-Za-z][A-Za-z'-]+", name or "")


def _has_full_name(name: str) -> bool:
    return len(_name_tokens(name)) >= 2


def _weak_byline(name: str) -> bool:
    normalized = " ".join(_name_tokens(name)).lower()
    if normalized in WEAK_BYLINES:
        return True
    return len(_name_tokens(name)) < 2


def _has_reviewer_fallback(evidence: dict[str, Any], voice_meta: dict[str, Any]) -> bool:
    reviewer = evidence.get("reviewer") if isinstance(evidence, dict) else None
    if isinstance(reviewer, dict) and _has_full_name(_text(reviewer.get("name") or reviewer.get("display_name"))):
        return True
    for key in ("reviewers", "reviewer_fallbacks"):
        values = voice_meta.get(key) if isinstance(voice_meta, dict) else None
        if isinstance(values, list) and any(isinstance(item, dict) and _has_full_name(_text(item.get("name") or item.get("display_name") or item.get("full_name"))) for item in values):
            return True
    return False


def _cta(article: dict[str, Any]) -> tuple[str, bool]:
    cta = _as_dict(article.get("cta"))
    primary = cta.get("primary")
    text = _text(primary)
    has_link = bool(cta.get("url") or cta.get("href") or cta.get("link"))
    if isinstance(primary, dict):
        text = _text(primary.get("text") or primary.get("label") or primary.get("title"))
        has_link = has_link or bool(primary.get("url") or primary.get("href") or primary.get("link"))
    return text, has_link


def _generic_cta(text: str) -> bool:
    return _text(text).lower() in {"get started", "start now", "learn more", "try it", "sign up"}


def _updated_at(article: dict[str, Any], schema_types: set[str]) -> bool:
    trust = _as_dict(article.get("trust"))
    if _text(trust.get("updated_at") or article.get("updated_at") or article.get("dateModified")):
        return True
    schema = _as_dict(article.get("schema"))
    return bool(_text(schema.get("dateModified") or schema.get("date_modified")))


def _internal_links(article: dict[str, Any]) -> list[str]:
    links = _as_dict(article.get("links")).get("internal")
    if isinstance(links, list):
        return [str(item) for item in links if item]
    return []


def _inbound_internal_links(article: dict[str, Any]) -> list[str]:
    links = _as_dict(article.get("links")).get("inbound_internal")
    if isinstance(links, list):
        return [str(item) for item in links if item]
    return []
