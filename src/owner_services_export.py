"""Offline export: existing evidence in, PDFs and companion indexes out.

Usage: python -m src.owner_services_export --udr-payload /path/to/read-only-evidence.json
No database access, benchmark calls, report snapshot persistence or raw-data edits.
"""
from __future__ import annotations
import argparse
from copy import deepcopy
import json
from pathlib import Path

from src.owner_services_report import FORMAT, build_owner_report, evidence_index_html
from src.owner_services_synthetic import synthetic_owner_services_payload
from src.poc_audit_pdf import render_poc_audit_pdf
from src.poc_audit_udr_owner_services import OWNER_REPORT, RUN_ID, TARGET_PLACE_ID


def prepare_udr_payload(evidence):
    if evidence["audit"]["baseline_run_id"] != RUN_ID or evidence["audit"]["target_google_place_id"] != TARGET_PLACE_ID:
        raise ValueError("This export requires the specified existing UDR benchmark and canonical identity")
    payload = deepcopy(evidence)
    payload["report"]["report_format"] = FORMAT
    payload["report"]["owner_report"] = deepcopy(OWNER_REPORT)
    # The mode was verified from the existing run configuration, not inferred
    # from answer wording. Legacy assembled payloads omitted this field.
    payload["methodology"].setdefault("benchmark_mode", OWNER_REPORT["benchmark_mode"])
    report = build_owner_report(payload)
    if (report["appearances"], report["answers"]) != (17, 72):
        raise ValueError("UDR evidence no longer reconciles with the reviewed 17/72 finding; investigate before export")
    return payload


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--udr-payload", required=True, type=Path)
    parser.add_argument("--output-dir", type=Path, default=Path("output/pdf"))
    args = parser.parse_args()
    udr = prepare_udr_payload(json.loads(args.udr_payload.read_text()))
    synthetic = synthetic_owner_services_payload()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    for payload, filename in [(udr, "UDR Properties - AI Visibility Report - V2.pdf"),
                              (synthetic, "Owner Services Template - V4 - Synthetic.pdf")]:
        (args.output_dir / filename).write_bytes(render_poc_audit_pdf(payload))
        (args.output_dir / payload["report"]["owner_report"]["evidence_index"]).write_text(evidence_index_html(payload), encoding="utf-8")
        print(filename)


if __name__ == "__main__":
    main()
