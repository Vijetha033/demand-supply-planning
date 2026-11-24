"""The five labelled edge cases: injected cleanly, traceable, detected with the right decision."""
import pandas as pd
import pytest

from supply_planning.edge_cases import inject_edge_cases
from supply_planning.generator import BaselineGenerator
from supply_planning.planning import run_planning
from supply_planning.schema import EDGE_CASE_TYPES, INPUT_TABLES, TABLES

EXPECTED = {"INBOUND_DOUBLE_COUNT": "EXCLUDE_DUPLICATE_INBOUND",
            "SUBSTITUTE_NOT_APPROVED": "REJECT_SUBSTITUTE_MITIGATION",
            "SUPPLIER_CAPACITY_EXCEEDED": "DEFER_EXCESS_TO_NEXT_AVAILABLE_WEEK",
            "SHORTAGE_WITHOUT_LEAD_TIME": "RECALCULATE_RECEIPT_WITH_LEAD_TIME"}


@pytest.mark.parametrize("issue_type", EDGE_CASE_TYPES)
def test_edge_case_labelled_and_detected(run, cfg, issue_type):
    gt, issues = run["gt"], run["outputs"]["detected_issue"]
    g = gt[gt.issue_type == issue_type]
    assert len(g) == cfg.edge_cases_per_type
    d = issues[issues.issue_type == issue_type].set_index("record_id")
    for r in g.itertuples():
        assert r.record_id in d.index, f"{issue_type} {r.record_id} not detected"
        assert d.at[r.record_id, "decision"] == r.expected_decision
        if issue_type in EXPECTED:
            assert r.expected_decision == EXPECTED[issue_type]
    assert set(d.index) == set(g.record_id), "no false positives"


def test_labels_trace_to_source_records(run):
    t, gt = run["inputs"], run["gt"]
    all_ids = set()
    for n in INPUT_TABLES:
        all_ids |= set(t[n][TABLES[n].primary_key])
    for r in gt[gt.label_category == "EDGE_CASE"].itertuples():
        assert r.record_id in all_ids
        for rel in str(r.related_record_ids).split("|"):
            assert rel in all_ids, f"{r.gt_id}: related id {rel} missing"


def test_injection_does_not_modify_baseline_rows(cfg):
    base, hidden = BaselineGenerator(cfg).run()
    snapshot = {n: base[n].copy() for n in INPUT_TABLES}
    st = run_planning(base)
    final, gt = inject_edge_cases(base, hidden, cfg, st)
    for n in INPUT_TABLES:
        pk = TABLES[n].primary_key
        before = snapshot[n].set_index(pk).sort_index()
        after = final[n].set_index(pk).loc[before.index]
        pd.testing.assert_frame_equal(before, after[before.columns], check_dtype=False)
        assert len(final[n]) >= len(snapshot[n])


def test_engine_corrections_change_the_plan(run):
    sr = run["outputs"]["scheduled_receipt"].set_index("po_line_id")
    gt = run["gt"]
    for r in gt[gt.issue_type == "UOM_MISMATCH"].itertuples():
        assert sr.at[r.record_id, "planning_base_qty"] == int(r.expected_value)
    for r in gt[gt.issue_type == "SHORTAGE_WITHOUT_LEAD_TIME"].itertuples():
        line = sr[sr.po_id == r.record_id].iloc[0]
        assert line.planning_receipt_date >= r.expected_value
        assert line.planning_receipt_date > line.source_receipt_date
