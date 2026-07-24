"""Tương thích ngược chuẩn QTI 2.1.

Đề của nhà cung cấp có thể xuất theo QTI 2.1 (camelCase, không tiền tố ``qti-``:
``assessmentItem``, ``choiceInteraction``, ``simpleChoice``…) thay vì QTI 3.0
(kebab-case ``qti-…``). Loader phải nạp CẢ HAI — chỉ khác cách gọi tên, logic
giống nhau. Đây là test đơn vị thuần (không DB / event loop).
"""

import os

import pytest

from app.services import qti_loader
from app.services.qti_loader import QtiLoadError

# --- gói QTI 2.1 tổng hợp (đúng phong cách file nhà cung cấp) -----------------

_MANIFEST_21 = """<?xml version="1.0" encoding="UTF-8"?>
<manifest xmlns="http://www.imsglobal.org/xsd/imscp_v1p1" identifier="m1">
  <metadata><schemaversion>2.1.0</schemaversion></metadata>
  <organizations/>
  <resources>
    <resource identifier="test_001" type="imsqti_test_xmlv2p1" href="tests/test_001.xml">
      <file href="tests/test_001.xml"/>
    </resource>
    <resource identifier="item_Q-1" type="imsqti_item_xmlv2p1" href="items/item_Q-1.xml">
      <file href="items/item_Q-1.xml"/>
    </resource>
    <resource identifier="item_Q-2" type="imsqti_item_xmlv2p1" href="items/item_Q-2.xml">
      <file href="items/item_Q-2.xml"/>
    </resource>
  </resources>
</manifest>
"""

# Section dùng THUỘC TÍNH ordering="random" (biến thể nhà cung cấp 2.1), không phải
# phần tử con <ordering>. Đáp án đúng nằm trong correctResponse→value (không tiền tố).
_TEST_21 = """<?xml version="1.0" encoding="UTF-8"?>
<assessmentTest xmlns="http://www.imsglobal.org/xsd/imsqti_v2p1" identifier="test_001" title="Đề 2.1">
  <testPart identifier="part1" navigationMode="linear" submissionMode="individual">
    <assessmentSection identifier="section1" title="Main" visible="true" ordering="random">
      <assessmentItemRef identifier="item_Q-1" href="items/item_Q-1.xml"/>
      <assessmentItemRef identifier="item_Q-2" href="items/item_Q-2.xml"/>
    </assessmentSection>
  </testPart>
</assessmentTest>
"""

_ITEM_21 = """<?xml version="1.0" encoding="UTF-8"?>
<assessmentItem xmlns="http://www.imsglobal.org/xsd/imsqti_v2p1" identifier="{ident}" title="{ident}">
  <responseDeclaration identifier="RESPONSE" cardinality="single" baseType="identifier">
    <correctResponse>
      <value>{correct}</value>
    </correctResponse>
  </responseDeclaration>
  <outcomeDeclaration identifier="SCORE" cardinality="single" baseType="float">
    <defaultValue><value>0</value></defaultValue>
  </outcomeDeclaration>
  <itemBody>
    <div class="stem">Câu {ident} — nội dung.</div>
    <p class="lead-in">Chọn đáp án đúng?</p>
    <choiceInteraction responseIdentifier="RESPONSE" shuffle="true" minChoices="1" maxChoices="1">
      <simpleChoice identifier="A">alpha</simpleChoice>
      <simpleChoice identifier="B">beta</simpleChoice>
      <simpleChoice identifier="C">gamma</simpleChoice>
      <simpleChoice identifier="D" fixed="true">Tất cả đáp án trên</simpleChoice>
    </choiceInteraction>
  </itemBody>
  <responseProcessing template="http://www.imsglobal.org/question/qti_v2p1/rptemplates/match_correct"/>
</assessmentItem>
"""


def _write_pkg_21(root: str, test_xml: str = _TEST_21) -> None:
    os.makedirs(os.path.join(root, "tests"))
    os.makedirs(os.path.join(root, "items"))
    with open(os.path.join(root, "imsmanifest.xml"), "w") as fh:
        fh.write(_MANIFEST_21)
    with open(os.path.join(root, "tests", "test_001.xml"), "w") as fh:
        fh.write(test_xml)
    for ident, correct in (("item_Q-1", "B"), ("item_Q-2", "C")):
        with open(os.path.join(root, "items", f"{ident}.xml"), "w") as fh:
            fh.write(_ITEM_21.format(ident=ident, correct=correct))


def test_loads_qti21_package(tmp_path):
    """Nạp gói 2.1 tổng hợp: đúng số câu, tên đề, đáp án đúng, 4 lựa chọn."""
    root = str(tmp_path)
    _write_pkg_21(root)
    parsed = qti_loader.load_qti_package(root)

    assert parsed["exam"]["name"] == "Đề 2.1"
    questions = sorted(parsed["payload"]["questions"], key=lambda q: q["order_index"])
    assert len(questions) == 2
    assert [q["code"] for q in questions] == ["item_Q-1", "item_Q-2"]
    # correctResponse→value (camelCase, không tiền tố) đọc đúng.
    assert questions[0]["correct_option"] == "B"
    assert questions[1]["correct_option"] == "C"
    # 4 lựa chọn A–D map đúng.
    assert [o["id"] for o in questions[0]["options"]] == ["A", "B", "C", "D"]
    assert questions[0]["options"][0]["text"] == "alpha"


def test_qti21_shuffle_flags(tmp_path):
    """Đảo câu bật từ thuộc tính section ordering="random"; đảo đáp án từ
    shuffle="true" trên choiceInteraction; fixed="true" đọc đúng."""
    root = str(tmp_path)
    _write_pkg_21(root)
    parsed = qti_loader.load_qti_package(root)

    assert parsed["exam"]["shuffle_questions"] is True   # section ordering="random"
    assert parsed["exam"]["shuffle_options"] is True     # choiceInteraction shuffle
    q0 = sorted(parsed["payload"]["questions"], key=lambda q: q["order_index"])[0]
    assert q0["options"][3]["fixed"] is True             # simpleChoice D fixed
    assert q0["options"][0]["fixed"] is False


def test_qti21_no_shuffle_when_section_ordering_absent(tmp_path):
    """Không có ordering="random" → đảo câu TẮT (mặc định do file quyết — AD-34)."""
    root = str(tmp_path)
    test_no_order = _TEST_21.replace(' ordering="random"', "")
    _write_pkg_21(root, test_xml=test_no_order)
    parsed = qti_loader.load_qti_package(root)
    assert parsed["exam"]["shuffle_questions"] is False


def test_qti21_rejects_selection(tmp_path):
    """selection (chọn ngẫu nhiên N câu) trong 2.1 cũng bị chặn như 3.0."""
    root = str(tmp_path)
    test_sel = _TEST_21.replace(
        '<assessmentItemRef identifier="item_Q-1"',
        '<selection select="1"/><assessmentItemRef identifier="item_Q-1"',
    )
    _write_pkg_21(root, test_xml=test_sel)
    with pytest.raises(QtiLoadError, match="selection"):
        qti_loader.load_qti_package(root)
