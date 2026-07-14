"""QTI fidelity tests: the deterministic shuffle must honour ``fixed="true"``
on both options and questions, and the loader must reject constructs it cannot
faithfully represent (qti-selection) rather than silently delivering all items.

These are pure unit tests — no DB / event loop needed."""

import os

import pytest

from app.services import qti_loader
from app.services.qti_loader import QtiLoadError
from app.services.session_service import build_orders, shuffle_keeping_fixed


# --- deterministic shuffle ---------------------------------------------------

def test_shuffle_keeping_fixed_pins_positions():
    items = ["A", "B", "C", "D"]
    fixed = [False, False, False, True]  # D pinned at the last slot
    out = shuffle_keeping_fixed("seed-1", items, fixed)
    assert out[3] == "D"
    assert sorted(out) == ["A", "B", "C", "D"]
    # Deterministic: same seed → same result (reload safety).
    assert out == shuffle_keeping_fixed("seed-1", items, fixed)


def test_shuffle_all_fixed_is_identity():
    items = ["A", "B", "C", "D"]
    assert shuffle_keeping_fixed("s", items, [True] * 4) == items


def test_build_orders_option_fixed_stays_put():
    payload = {"questions": [{
        "id": "q1", "order_index": 0, "fixed": False,
        "options": [
            {"id": "A", "fixed": False}, {"id": "B", "fixed": False},
            {"id": "C", "fixed": False}, {"id": "D", "fixed": True},
        ],
    }]}
    _, option_order = build_orders("sess-1", payload, shuffle_q=False, shuffle_o=True)
    assert option_order["q1"][3] == "D"
    assert sorted(option_order["q1"]) == ["A", "B", "C", "D"]


def test_build_orders_question_fixed_stays_put():
    qs = [{"id": f"q{i}", "order_index": i, "fixed": (i == 0), "options": []}
          for i in range(6)]
    question_order, _ = build_orders("sx", {"questions": qs}, shuffle_q=True, shuffle_o=False)
    assert question_order[0] == "q0"  # pinned first
    assert sorted(question_order) == sorted(q["id"] for q in qs)


def test_build_orders_legacy_payload_without_fixed():
    """Old payloads (imported before fixed support) have no ``fixed`` keys —
    must still shuffle as a permutation, treating everything as movable."""
    payload = {"questions": [{
        "id": "q1", "order_index": 0,
        "options": [{"id": c} for c in ("A", "B", "C", "D")],
    }]}
    _, option_order = build_orders("s", payload, shuffle_q=False, shuffle_o=True)
    assert sorted(option_order["q1"]) == ["A", "B", "C", "D"]


# --- loader: synthetic QTI package -------------------------------------------

_MANIFEST = """<?xml version="1.0"?>
<manifest xmlns="http://www.imsglobal.org/xsd/imscp_v1p1">
  <resources>
    <resource type="imsqti_test_xmlv3p0" href="tests/test1.xml"/>
  </resources>
</manifest>
"""

_ITEM = """<?xml version="1.0"?>
<qti-assessment-item identifier="{ident}">
  <qti-response-declaration identifier="RESPONSE" cardinality="single" base-type="identifier">
    <qti-correct-response><qti-value>A</qti-value></qti-correct-response>
  </qti-response-declaration>
  <qti-item-body>
    <p class="stem">Question {ident}?</p>
    <qti-choice-interaction response-identifier="RESPONSE" shuffle="true" max-choices="1">
      <qti-simple-choice identifier="A">alpha</qti-simple-choice>
      <qti-simple-choice identifier="B">beta</qti-simple-choice>
      <qti-simple-choice identifier="C">gamma</qti-simple-choice>
      <qti-simple-choice identifier="D" fixed="true">none of the above</qti-simple-choice>
    </qti-choice-interaction>
  </qti-item-body>
</qti-assessment-item>
"""


def _write_pkg(root: str, test_xml: str) -> None:
    os.makedirs(os.path.join(root, "tests"))
    os.makedirs(os.path.join(root, "items"))
    with open(os.path.join(root, "imsmanifest.xml"), "w") as fh:
        fh.write(_MANIFEST)
    with open(os.path.join(root, "tests", "test1.xml"), "w") as fh:
        fh.write(test_xml)
    for ident in ("i1", "i2"):
        with open(os.path.join(root, "items", f"{ident}.xml"), "w") as fh:
            fh.write(_ITEM.format(ident=ident))


def test_loader_reads_fixed_on_choice_and_item(tmp_path):
    root = str(tmp_path)
    _write_pkg(root, """<?xml version="1.0"?>
<qti-assessment-test title="Synthetic">
  <qti-test-part>
    <qti-assessment-section>
      <qti-ordering shuffle="true"/>
      <qti-assessment-item-ref identifier="i1" href="../items/i1.xml" fixed="true"/>
      <qti-assessment-item-ref identifier="i2" href="../items/i2.xml"/>
    </qti-assessment-section>
  </qti-test-part>
</qti-assessment-test>
""")
    parsed = qti_loader.load_qti_package(root)
    assert parsed["exam"]["shuffle_questions"] is True
    assert parsed["exam"]["shuffle_options"] is True
    questions = sorted(parsed["payload"]["questions"], key=lambda q: q["order_index"])
    assert questions[0]["fixed"] is True   # i1 ref had fixed="true"
    assert questions[1]["fixed"] is False
    # The D choice carried fixed="true" in every item.
    assert questions[0]["options"][3]["fixed"] is True
    assert questions[0]["options"][0]["fixed"] is False


def test_loader_rejects_qti_selection(tmp_path):
    root = str(tmp_path)
    _write_pkg(root, """<?xml version="1.0"?>
<qti-assessment-test title="Synthetic">
  <qti-test-part>
    <qti-assessment-section>
      <qti-selection select="1"/>
      <qti-assessment-item-ref identifier="i1" href="../items/i1.xml"/>
      <qti-assessment-item-ref identifier="i2" href="../items/i2.xml"/>
    </qti-assessment-section>
  </qti-test-part>
</qti-assessment-test>
""")
    with pytest.raises(QtiLoadError, match="qti-selection"):
        qti_loader.load_qti_package(root)
