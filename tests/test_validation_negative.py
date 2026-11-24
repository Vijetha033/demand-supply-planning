"""Failure paths: the validator must catch corruption that is NOT labelled."""
import pandas as pd
import pytest

from supply_planning.validation import Validator


def _validate(run, mutate):
    t = {k: v.copy() for k, v in {**run["inputs"], **run["outputs"]}.items()}
    mutate(t)
    return Validator(t, run["gt"]).run(outputs=True, sqlite=False)


def test_duplicate_primary_key_detected(run):
    def m(t):
        t["sku"] = pd.concat([t["sku"], t["sku"].iloc[[0]]], ignore_index=True)
    s = _validate(run, m)
    v = s["violations"]
    assert ((v.check == "pk:sku") & (v.classification == "UNEXPECTED")).any()
    assert s["overall_status"] == "FAIL"


def test_orphan_foreign_key_detected(run):
    def m(t):
        t["purchase_order_line"].loc[0, "sku_id"] = "SKU-999999"
    v = _validate(run, m)["violations"]
    assert v.check.str.startswith("fk:purchase_order_line.sku_id").any()


def test_bad_enum_detected(run):
    def m(t):
        t["purchase_order"].loc[0, "status"] = "LOST"
    v = _validate(run, m)["violations"]
    assert ((v.check == "schema:purchase_order") & v.detail.str.contains("allowed")).any()


def test_broken_pab_arithmetic_detected(run):
    def m(t):
        t["projected_balance"].loc[5, "closing_balance"] += 7
    v = _validate(run, m)["violations"]
    assert (v.check == "reconciliation:pab_weekly").any()


def test_invalid_lifecycle_transition_detected(run):
    def m(t):
        ev = t["purchase_order_event"]
        i = ev.index[ev.event_type == "RECEIVED"][0]
        ev.loc[i, "from_status"] = "PLANNED"
    v = _validate(run, m)["violations"]
    assert (v.check == "lifecycle:po_events").any()


def test_date_ordering_detected(run):
    def m(t):
        po = t["purchase_order"]
        po.loc[0, "ship_date"] = "2020-01-01"
    v = _validate(run, m)["violations"]
    assert (v.check == "date:purchase_order").any()
