"""Closed vocabularies are declared in three places — YAML (authoring), JSON Schema
(LLM output validation) and SQL (storage enforcement). They must never drift.

Drift here is silent and expensive: the pipeline accepts a predicate the database rejects,
or the database accepts one no query knows about. These tests are the tripwire.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml")

ROOT = Path(__file__).resolve().parents[1]
SQL = (ROOT / "db/migrations/001_init.sql").read_text()


def _sql_enum(name: str) -> set[str]:
    match = re.search(rf"CREATE TYPE {name} AS ENUM \((.*?)\);", SQL, re.S)
    assert match, f"enum {name} not found in migration"
    return set(re.findall(r"'([a-z_]+)'", match.group(1)))


def _yaml(path: str) -> dict:
    return yaml.safe_load((ROOT / path).read_text())


def _json(path: str) -> dict:
    return json.loads((ROOT / path).read_text())


def test_relation_predicates_consistent() -> None:
    spec = _yaml("taxonomy/relation_types.yaml")
    from_yaml = {p for group in spec["groups"].values() for p in group["predicates"]}
    from_json = set(_json("schemas/json/relation.schema.json")["$defs"]["predicate"]["enum"])
    from_sql = _sql_enum("relation_predicate_t")

    assert from_yaml == from_json, f"yaml/json drift: {from_yaml ^ from_json}"
    assert from_yaml == from_sql, f"yaml/sql drift: {from_yaml ^ from_sql}"


def test_entity_types_consistent() -> None:
    from_yaml = set(_yaml("taxonomy/entity_types.yaml")["types"])
    from_json = set(_json("schemas/json/entity.schema.json")["properties"]["entity_type"]["enum"])
    from_sql = _sql_enum("entity_type_t")

    assert from_yaml == from_json, f"yaml/json drift: {from_yaml ^ from_json}"
    assert from_yaml == from_sql, f"yaml/sql drift: {from_yaml ^ from_sql}"


def test_domain_codes_consistent() -> None:
    from_yaml = {d["code"] for d in _yaml("taxonomy/taxonomy.yaml")["domains"]}
    from_json = set(_json("schemas/json/knowledge_card.schema.json")["properties"]["domain"]["enum"])

    assert from_yaml == from_json, f"drift: {from_yaml ^ from_json}"

    from lashos_ke.core.ids import _VALID_DOMAINS

    assert from_yaml == set(_VALID_DOMAINS), f"ids.py drift: {from_yaml ^ set(_VALID_DOMAINS)}"


def test_domain_codes_are_unique_and_three_letters() -> None:
    domains = _yaml("taxonomy/taxonomy.yaml")["domains"]
    codes = [d["code"] for d in domains]
    assert len(codes) == len(set(codes)), "duplicate domain codes"
    assert all(re.fullmatch(r"[A-Z]{3}", c) for c in codes)


def test_every_domain_has_a_recency_halflife() -> None:
    """Confidence scoring reads a half-life per domain; a missing one silently
    falls back to a default and mis-ages that domain's knowledge."""
    from lashos_ke.core.confidence import DOMAIN_HALFLIFE_YEARS

    for domain in _yaml("taxonomy/taxonomy.yaml")["domains"]:
        assert domain["code"] in DOMAIN_HALFLIFE_YEARS, f"no half-life for {domain['code']}"
        assert domain["recency_halflife_years"] == DOMAIN_HALFLIFE_YEARS[domain["code"]], (
            f"half-life mismatch for {domain['code']}: "
            f"taxonomy={domain['recency_halflife_years']} "
            f"code={DOMAIN_HALFLIFE_YEARS[domain['code']]}"
        )


def test_evidence_tiers_consistent() -> None:
    from lashos_ke.core.confidence import EVIDENCE_TIER_WEIGHT

    from_json = set(_json("schemas/json/claim.schema.json")["properties"]["evidence_tier"]["enum"])
    from_sql = _sql_enum("evidence_tier_t")

    from lashos_ke.extract.validators import VALID_EVIDENCE_TIERS

    assert from_json == from_sql, f"json/sql drift: {from_json ^ from_sql}"
    assert from_json == set(EVIDENCE_TIER_WEIGHT), (
        f"confidence.py drift: {from_json ^ set(EVIDENCE_TIER_WEIGHT)}"
    )
    assert from_json == VALID_EVIDENCE_TIERS, (
        f"validators.py drift: {from_json ^ VALID_EVIDENCE_TIERS}"
    )


def test_every_domain_has_a_vault_folder() -> None:
    folders = [d["folder"] for d in _yaml("taxonomy/taxonomy.yaml")["domains"]]
    assert len(folders) == len(set(folders)), "duplicate vault folders"
    assert all(re.fullmatch(r"\d{2}-[A-Za-z-]+", f) for f in folders)
