"""Lightweight evaluation harness.

Compares the JSON snapshots produced by ``main.py`` against hand-labeled
expected JSON. Reports per-contract field matches and aggregate scores so
you can tell whether a prompt change is actually helping.

Expected files live in a folder, one per contract, named
``<contract_id>.expected.json``. Each is a partial ``ContractExtraction``:
include only the fields you want to assert. Anything not present is ignored.

Example expected file::

    {
      "patch_management": {
        "required": true,
        "pricing_model": "included",
        "end_date": "2027-12-31"
      },
      "commercial_risk_flags": ["lump_sum_warranty"],
      "not_found": []
    }

For ``commercial_risk_flags`` the expected value is a list of risk_type
strings; the predicted set's precision/recall against it is computed.

Usage:

    python -m contract_inventory.evaluate \\
        --predicted ./sp7_inventory_json \\
        --expected ./eval
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class FieldResult:
    field: str
    expected: Any
    actual: Any
    match: bool


@dataclass
class ContractReport:
    contract_id: str
    fields: list[FieldResult] = field(default_factory=list)
    risk_precision: float | None = None
    risk_recall: float | None = None

    @property
    def field_match_count(self) -> int:
        return sum(1 for f in self.fields if f.match)

    @property
    def field_total(self) -> int:
        return len(self.fields)


SCALAR_FIELDS = [
    ("patch_management.required", ["patch_management", "required"]),
    ("patch_management.pricing_model", ["patch_management", "pricing_model"]),
    ("patch_management.end_date", ["patch_management", "end_date"]),
    ("base_package.scope_summary_present", ["base_package", "scope_summary"]),
    ("confidence", ["confidence"]),
]


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    predicted_dir = Path(args.predicted)
    expected_dir = Path(args.expected)

    expected_files = sorted(expected_dir.glob("*.expected.json"))
    if not expected_files:
        print(f"No expected files in {expected_dir}", file=sys.stderr)
        return 1

    reports: list[ContractReport] = []
    for ep in expected_files:
        contract_id = ep.name.replace(".expected.json", "")
        predicted_path = predicted_dir / f"{contract_id}.json"
        if not predicted_path.exists():
            print(f"[skip] no prediction for {contract_id} ({predicted_path})",
                  file=sys.stderr)
            continue
        expected = json.loads(ep.read_text(encoding="utf-8"))
        actual = json.loads(predicted_path.read_text(encoding="utf-8"))
        reports.append(_compare_one(contract_id, expected, actual))

    _print_per_contract(reports)
    _print_aggregate(reports)
    return 0 if all(_passed(r) for r in reports) else 2


def _compare_one(contract_id: str, expected: dict, actual: dict) -> ContractReport:
    report = ContractReport(contract_id=contract_id)

    # Scalar / nested-scalar fields
    for label, keys in SCALAR_FIELDS:
        if not _present(expected, keys):
            continue
        exp_v = _dig(expected, keys)
        act_v = _dig(actual, keys)
        if label.endswith("_present"):
            # Just check presence/non-emptiness when expected is True/False
            act_present = bool(act_v)
            match = bool(exp_v) == act_present
            report.fields.append(FieldResult(label, exp_v, act_v, match))
        else:
            report.fields.append(FieldResult(label, exp_v, act_v, exp_v == act_v))

    # not_found set match
    if "not_found" in expected:
        exp_set = set(expected["not_found"])
        act_set = set(actual.get("not_found", []))
        report.fields.append(FieldResult(
            "not_found", sorted(exp_set), sorted(act_set), exp_set == act_set,
        ))

    # commercial_risk_flags: precision/recall on risk_type set
    if "commercial_risk_flags" in expected:
        exp_types = set(expected["commercial_risk_flags"])
        act_types = {flag.get("risk_type") for flag in actual.get("commercial_risk_flags", [])}
        act_types.discard(None)
        tp = len(exp_types & act_types)
        report.risk_precision = tp / len(act_types) if act_types else (1.0 if not exp_types else 0.0)
        report.risk_recall = tp / len(exp_types) if exp_types else 1.0

    return report


def _passed(r: ContractReport) -> bool:
    if r.field_total and r.field_match_count != r.field_total:
        return False
    if r.risk_precision is not None and r.risk_precision < 1.0:
        return False
    if r.risk_recall is not None and r.risk_recall < 1.0:
        return False
    return True


def _print_per_contract(reports: list[ContractReport]) -> None:
    print("=" * 78)
    print("PER-CONTRACT REPORT")
    print("=" * 78)
    for r in reports:
        print(f"\n{r.contract_id}: {r.field_match_count}/{r.field_total} fields match")
        for f in r.fields:
            mark = "OK " if f.match else "X  "
            print(f"  [{mark}] {f.field}: expected={f.expected!r} actual={f.actual!r}")
        if r.risk_precision is not None:
            print(f"  commercial_risk_flags: precision={r.risk_precision:.2f} "
                  f"recall={r.risk_recall:.2f}")


def _print_aggregate(reports: list[ContractReport]) -> None:
    print("\n" + "=" * 78)
    print("AGGREGATE")
    print("=" * 78)
    total = sum(r.field_total for r in reports)
    matched = sum(r.field_match_count for r in reports)
    print(f"Field matches: {matched}/{total}"
          + (f"  ({matched/total:.0%})" if total else ""))

    risk_reports = [r for r in reports if r.risk_precision is not None]
    if risk_reports:
        avg_p = sum(r.risk_precision for r in risk_reports) / len(risk_reports)
        avg_r = sum(r.risk_recall for r in risk_reports) / len(risk_reports)
        print(f"Risk-type avg precision: {avg_p:.2f}  avg recall: {avg_r:.2f}")

    failed = [r.contract_id for r in reports if not _passed(r)]
    if failed:
        print(f"Failing: {', '.join(failed)}")
    else:
        print("All contracts pass.")


def _present(d: dict, keys: list[str]) -> bool:
    cur: Any = d
    for k in keys:
        if not isinstance(cur, dict) or k not in cur:
            return False
        cur = cur[k]
    return True


def _dig(d: dict, keys: list[str]) -> Any:
    cur: Any = d
    for k in keys:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(k)
    return cur


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Evaluate predictions against expected JSON")
    p.add_argument("--predicted", required=True, help="Directory of predicted JSON")
    p.add_argument("--expected", required=True, help="Directory of <id>.expected.json files")
    return p.parse_args(argv)


if __name__ == "__main__":
    sys.exit(main())
