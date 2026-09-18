import asyncio
import hashlib
import json
from pathlib import Path

import fitz
from jsonschema import Draft202012Validator

from app.models import KnowledgeTree
from app.parsing.formatted_text_parser import FormattedTextParser
from scripts.build_public_fixture import DEFAULT_SPEC, build_fixture
from scripts.evaluate_live_public_fixture import compare_complete_tree
from scripts.evaluate_public_fixture import evaluate, load_gold
from scripts.run_public_demo import EXPECTED_OUTPUT, run_demo

ROOT = Path(__file__).resolve().parents[2]


def test_public_regression_reference_has_41_unique_human_readable_assertions():
    gold = load_gold(ROOT / "evaluation" / "gold" / "public_fixture_gold.jsonl")
    assert len(gold) == 41
    assert len({item["id"] for item in gold}) == 41
    assert {item["kind"] for item in gold} == {"node", "scope"}


def test_frozen_protocol_matches_public_regression_reference():
    parsed = FormattedTextParser().parse(
        EXPECTED_OUTPUT.read_text(encoding="utf-8"), "公开合成 fixture"
    )
    result = evaluate(
        parsed.tree.model_dump(mode="json"),
        load_gold(ROOT / "evaluation" / "gold" / "public_fixture_gold.jsonl"),
    )
    assert result["assertion_count"] == 41
    assert result["failed_count"] == 0


def test_complete_tree_comparison_detects_extra_and_missing_nodes():
    gold = [
        {"id": "G001", "kind": "node", "path": ["根"]},
        {"id": "G002", "kind": "node", "path": ["根", "节点"]},
        {
            "id": "G003",
            "kind": "scope",
            "path": ["根", "节点"],
            "expected": "原文",
        },
    ]
    exact = {
        "children": [
            {
                "name": "根",
                "scope": None,
                "children": [{"name": "节点", "scope": "原文", "children": []}],
            }
        ]
    }

    matched = compare_complete_tree(exact, gold)
    assert matched["exact_tree_match"] is True
    assert matched["node_f1"] == 1.0
    assert matched["scope_exact_accuracy"] == 1.0
    assert matched["unique_root"] is True

    exact["children"][0]["children"].append(
        {"name": "多余节点", "scope": None, "children": []}
    )
    drifted = compare_complete_tree(exact, gold)
    assert drifted["exact_tree_match"] is False
    assert drifted["extra_paths"] == [["根", "多余节点"]]


def test_public_demo_runs_real_preparation_and_publication_path(tmp_path):
    fixture = build_fixture(DEFAULT_SPEC, tmp_path / "fixture.pdf")
    with fitz.open(fixture) as document:
        assert all(
            any(
                font[1] != "n/a" and font[2] in {"TrueType", "CIDFontType2"}
                for font in page.get_fonts(full=True)
            )
            for page in document
        )
    summary = asyncio.run(run_demo(tmp_path / "demo", fixture))
    assert summary["image_count"] == 2
    assert summary["node_count"] == 33
    assert summary["leaf_count"] == 24
    assert summary["warning_count"] == 0
    assert summary["error_count"] == 0
    assert (tmp_path / "demo" / "artifacts" / "run_report.json").is_file()
    layout_profile = json.loads(
        (tmp_path / "demo" / "artifacts" / "layout_profile.json").read_text(
            encoding="utf-8"
        )
    )
    layout_schema = json.loads(
        (ROOT / "schemas" / "layout_profile.schema.json").read_text(encoding="utf-8")
    )
    Draft202012Validator(layout_schema).validate(layout_profile)
    assert layout_profile["document_identity"]["root_labels"] == [
        "合成初中数学课程纲要（公开评测版）"
    ]
    assert [item["label"] for item in layout_profile["range_labels"]] == [
        "七年级上册",
        "七年级下册",
    ]
    tree = json.loads(
        (tmp_path / "demo" / "artifacts" / "knowledge_tree.json").read_text(
            encoding="utf-8"
        )
    )
    assert len(tree["children"]) == 1


def test_versioned_junior_release_contract():
    release_dir = ROOT / "releases" / "v1.0.0"
    artifact = release_dir / "KT_MICSS_junior.json"
    manifest = json.loads(
        (release_dir / "KT_MICSS_junior.manifest.json").read_text(encoding="utf-8")
    )
    tree = KnowledgeTree.model_validate_json(artifact.read_text(encoding="utf-8"))
    tree_schema = json.loads(
        (ROOT / "schemas" / "knowledge_tree.schema.json").read_text(encoding="utf-8")
    )
    manifest_schema = json.loads(
        (ROOT / "schemas" / "release_manifest.schema.json").read_text(encoding="utf-8")
    )
    Draft202012Validator.check_schema(tree_schema)
    Draft202012Validator.check_schema(manifest_schema)
    Draft202012Validator(tree_schema).validate(tree.model_dump(mode="json"))
    Draft202012Validator(manifest_schema).validate(manifest)
    assert tree.children
    assert manifest["manifest_schema_version"] == "1.0.0"
    assert manifest["knowledge_tree_schema_version"] == "1.0.0"
    assert manifest["catalog_version"] == "1.0.0"
    assert manifest["logical_name"] == "KT_MICSS_junior"
    assert manifest["compatibility"] == {
        "canonical_request": "KT_MICSS_junior",
        "legacy_request": "KT_MICSS_junior.json",
    }
    assert hashlib.sha256(artifact.read_bytes()).hexdigest() == manifest["artifact_sha256"]
    assert manifest["source"]["included"] is False


def test_layout_profile_schema_is_valid():
    schema = json.loads(
        (ROOT / "schemas" / "layout_profile.schema.json").read_text(encoding="utf-8")
    )
    Draft202012Validator.check_schema(schema)
