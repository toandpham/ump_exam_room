"""Load an IMS QTI content package (3.0 hoặc 2.1) và chuyển thành payload đề nội
bộ dùng cho phần còn lại của hệ thống.

Hỗ trợ CẢ HAI phiên bản chuẩn QTI:
  * QTI 3.0 — tên phần tử kebab-case có tiền tố ``qti-`` (``qti-assessment-item``,
    ``qti-choice-interaction``, ``qti-simple-choice``…), thuộc tính ``max-choices``,
    ``response-identifier``…
  * QTI 2.1 — tên phần tử camelCase KHÔNG tiền tố (``assessmentItem``,
    ``choiceInteraction``, ``simpleChoice``…), thuộc tính ``maxChoices``,
    ``responseIdentifier``…

Cấu trúc logic của 2 phiên bản GIỐNG NHAU (1 đáp án đúng, 4 lựa chọn A–D, ảnh
inline ``<img>``); chỉ khác cách gọi tên nên loader khớp cả 2 bộ tên ở mỗi chỗ
(xem các hằng ``_TAG_*`` và ``_attr``). Namespace bị bỏ qua hoàn toàn
(so khớp theo localname) nên khác biệt namespace giữa 2 chuẩn không ảnh hưởng.

Package layout (giống nhau ở cả 3.0 và 2.1 — https://www.1edtech.org/standards/qti):

    <root>/
      imsmanifest.xml            <- lists every resource
      tests/<id>.xml             <- qti-assessment-test (ordered list of items)
      items/<id>.xml             <- qti-assessment-item (one question each)
      resources/...              <- inline media (images etc.)

We currently support single-choice (qti-choice-interaction with max-choices=1,
4 options labelled A/B/C/D) — the only shape this product cares about. Other
interaction types are ignored with a warning.

The loader returns a dict shaped exactly like the JSON the rest of the system
expects in Redis:

    {
      "exam": {"name", "duration_minutes", "exam_date", "shuffle_questions",
               "shuffle_options"},
      "payload": {"questions": [{"id","text","images":[{"b64","mime"}],
                  "correct_option","order_index","fixed","options":[
                    {"id","text","images":[{"b64","mime"}],"fixed"}
                  ]}]},

``fixed`` mirrors QTI ``fixed="true"`` and is honoured by the deterministic
shuffle (see ``session_service.build_orders``).
    }

so the existing ``exam_package`` encryption + activate flow can be reused
without changes.
"""

from __future__ import annotations

import base64
import logging
import os
import uuid
from xml.etree import ElementTree as ET

logger = logging.getLogger("exam.qti")

QTI_NS = "http://www.imsglobal.org/xsd/imsqtiasi_v3p0"
CP_NS = "http://www.imsglobal.org/xsd/imscp_v1p1"

_MIME = {
    ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
    ".gif": "image/gif", ".webp": "image/webp", ".svg": "image/svg+xml",
}

_OPTION_IDS = ("A", "B", "C", "D")

# Tên phần tử tương đương giữa QTI 3.0 (kebab-case, tiền tố ``qti-``) và QTI 2.1
# (camelCase, không tiền tố). Mỗi lookup chấp nhận CẢ HAI để tương thích ngược.
_TAG_ITEM = ("qti-assessment-item", "assessmentItem")
_TAG_ITEM_BODY = ("qti-item-body", "itemBody")
_TAG_INTERACTION = ("qti-choice-interaction", "choiceInteraction")
_TAG_CHOICE = ("qti-simple-choice", "simpleChoice")
_TAG_RESP_DECL = ("qti-response-declaration", "responseDeclaration")
_TAG_CORRECT = ("qti-correct-response", "correctResponse")
_TAG_VALUE = ("qti-value", "value")
_TAG_ITEM_REF = ("qti-assessment-item-ref", "assessmentItemRef")
_TAG_ORDERING = ("qti-ordering", "ordering")
_TAG_SELECTION = ("qti-selection", "selection")
_TAG_SECTION = ("qti-assessment-section", "assessmentSection")
_TAG_TIME_LIMITS = ("qti-time-limits", "timeLimits")


class QtiLoadError(Exception):
    """Malformed or unsupported QTI package."""


def _localname(tag: str) -> str:
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def _find(elem: ET.Element, *local_names: str) -> ET.Element | None:
    """Find the first descendant whose localname matches, ignoring namespaces."""
    for e in elem.iter():
        if _localname(e.tag) in local_names:
            return e
    return None


def _findall(elem: ET.Element, *local_names: str) -> list[ET.Element]:
    """Mọi hậu duệ có localname khớp một trong ``local_names`` (bỏ qua namespace)."""
    return [e for e in elem.iter() if _localname(e.tag) in local_names]


def _attr(elem: ET.Element, *names: str, default: str | None = None) -> str | None:
    """Đọc thuộc tính đầu tiên có mặt trong ``names`` (khớp tên 3.0 vs 2.1, vd
    ``max-choices`` / ``maxChoices``)."""
    for n in names:
        if n in elem.attrib:
            return elem.attrib[n]
    return default


# Thẻ HTML khối → chèn ký tự xuống dòng khi bóc chữ, để nội dung nhiều đoạn của đề
# QTI (vd phần "Xét nghiệm cận lâm sàng" nằm trong <div><p>…</p><p>…</p></div>)
# xuống dòng đúng như file gốc thay vì dồn thành một dòng (AD-97).
_BLOCK_TAGS = {"p", "div", "li", "ul", "ol", "tr", "table",
               "h1", "h2", "h3", "h4", "h5", "h6", "blockquote", "pre"}


def _norm_text(raw: str) -> str:
    """Chuẩn hoá 1 đoạn text: gộp khoảng trắng trong từng dòng, bỏ dòng trống →
    mỗi ý một dòng (\\n giữ nguyên; màn thi render whitespace-pre-wrap, AD-97)."""
    lines = [" ".join(ln.split()) for ln in raw.split("\n")]
    return "\n".join(ln for ln in lines if ln)


def _extract_blocks(elem: ET.Element, root_dir: str) -> list[dict]:
    """Bóc nội dung của ``elem`` thành DANH SÁCH KHỐI CÓ THỨ TỰ (AD-98):
    ``{"type":"text","text":…}`` và ``{"type":"image","b64":…,"mime":…}`` XEN KẼ
    ĐÚNG như trong file — nhờ đó ảnh nằm giữa/ cuối chữ giữ nguyên vị trí thay vì
    bị dồn xuống dưới. Ranh giới thẻ khối + <br/> thành ``\\n`` (như AD-97)."""
    blocks: list[dict] = []
    buf: list[str] = []

    def flush() -> None:
        if not buf:
            return
        text = _norm_text("".join(buf))
        buf.clear()
        if text:
            blocks.append({"type": "text", "text": text})

    def walk(e: ET.Element) -> None:
        tag = _localname(e.tag)
        if tag == "img":
            src = e.attrib.get("src") or e.attrib.get("{http://www.w3.org/1999/xhtml}src")
            if src:
                img = _load_image(os.path.join(root_dir, src))
                if img:
                    flush()   # chốt đoạn chữ trước ảnh → giữ đúng thứ tự
                    blocks.append({"type": "image", **img})
            # KHÔNG lấy alt của ảnh (thường là "Question attachment" — rác).
            if e.tail:
                buf.append(e.tail)
            return
        if tag == "br":
            buf.append("\n")
            if e.tail:
                buf.append(e.tail)
            return
        block = tag in _BLOCK_TAGS
        if block:
            buf.append("\n")
        if e.text:
            buf.append(e.text)
        for child in e:
            walk(child)
        if block:
            buf.append("\n")
        if e.tail:
            buf.append(e.tail)

    walk(elem)
    flush()
    return blocks


def _extract_text_and_images(elem: ET.Element, root_dir: str) -> tuple[str, list[dict]]:
    """Tương thích ngược: trả (text, images) gộp từ các khối. Text = nối các khối
    chữ bằng \\n; images = ảnh theo thứ tự. Dùng cho đáp án + nơi không cần khối."""
    blocks = _extract_blocks(elem, root_dir)
    text = "\n".join(b["text"] for b in blocks if b["type"] == "text")
    images = [{"b64": b["b64"], "mime": b["mime"]} for b in blocks if b["type"] == "image"]
    return text, images


def _safe_parse_root(path: str, what: str):
    """Parse 1 file XML, TỪ CHỐI nếu có DTD (AD-75, phòng thủ theo chiều sâu).

    ElementTree chuẩn không resolve external entity qua mạng, nhưng entity
    expansion / DTD vẫn có thể phình bộ nhớ. Gói QTI hợp lệ không bao giờ cần
    DOCTYPE nên chặn thẳng là an toàn nhất, không cần thêm dependency."""
    try:
        with open(path, "rb") as fh:
            data = fh.read()
    except OSError as exc:
        raise QtiLoadError(f"Không đọc được {what}: {exc}")
    if b"<!DOCTYPE" in data or b"<!ENTITY" in data:
        raise QtiLoadError(f"{what} chứa DTD/ENTITY — không phải file QTI hợp lệ.")
    try:
        return ET.fromstring(data)
    except ET.ParseError as exc:
        raise QtiLoadError(f"{what} không hợp lệ: {exc}")


def _load_image(abs_path: str) -> dict | None:
    if not os.path.isfile(abs_path):
        logger.warning("QTI image not found: %s", abs_path)
        return None
    ext = os.path.splitext(abs_path)[1].lower()
    mime = _MIME.get(ext, "application/octet-stream")
    with open(abs_path, "rb") as fh:
        data = fh.read()
    return {"b64": base64.b64encode(data).decode("ascii"), "mime": mime}


def _parse_item(item_path: str, root_dir: str, order_index: int) -> dict:
    """Convert a single qti-assessment-item XML into our question dict."""
    root = _safe_parse_root(item_path, f"câu hỏi {os.path.basename(item_path)}")
    if _localname(root.tag) not in _TAG_ITEM:
        raise QtiLoadError(f"File không phải assessment-item (QTI 3.0/2.1): {item_path}")

    body = _find(root, *_TAG_ITEM_BODY)
    if body is None:
        raise QtiLoadError(f"Câu hỏi thiếu item-body: {item_path}")

    # Nội dung câu hỏi = mọi khối trong item-body TRƯỚC phần đáp án, GIỮ NGUYÊN THỨ
    # TỰ (chữ ↔ ảnh xen kẽ) — AD-98. Trước đây gom hết chữ rồi dồn ảnh xuống cuối →
    # ảnh (vd hình siêu âm giữa "xét nghiệm" và "câu hỏi") bị rơi sai vị trí.
    raw_blocks: list[dict] = []
    for child in body:
        if _localname(child.tag) in _TAG_INTERACTION:
            break
        raw_blocks.extend(_extract_blocks(child, root_dir))

    # Tách ảnh ra mảng ``images`` (materialize/preload dùng), khối ảnh chỉ giữ CHỈ
    # SỐ trỏ vào mảng đó. ``text`` (nối các khối chữ) giữ cho báo cáo + tương thích.
    images: list[dict] = []
    blocks: list[dict] = []
    for b in raw_blocks:
        if b["type"] == "image":
            blocks.append({"type": "image", "index": len(images)})
            images.append({"b64": b["b64"], "mime": b["mime"]})
        else:
            blocks.append(b)
    text = "\n".join(b["text"] for b in blocks if b["type"] == "text").strip()

    interaction = _find(body, *_TAG_INTERACTION)
    if interaction is None:
        raise QtiLoadError(f"Câu hỏi không có choice-interaction: {item_path}")
    response_id = _attr(interaction, "response-identifier", "responseIdentifier",
                        default="RESPONSE")
    max_choices = int(_attr(interaction, "max-choices", "maxChoices") or "1")
    if max_choices != 1:
        raise QtiLoadError(
            f"Chỉ hỗ trợ câu hỏi 1 đáp án (max-choices=1), file: {item_path}"
        )
    shuffle_options = interaction.attrib.get("shuffle") == "true"

    choices = _findall(interaction, *_TAG_CHOICE)
    if not choices:
        raise QtiLoadError(f"Câu hỏi không có đáp án: {item_path}")
    if len(choices) != 4:
        raise QtiLoadError(
            f"Hệ thống yêu cầu đúng 4 đáp án A/B/C/D, file: {item_path} có {len(choices)}"
        )

    options: list[dict] = []
    id_to_letter: dict[str, str] = {}
    for letter, choice in zip(_OPTION_IDS, choices):
        raw_id = choice.attrib.get("identifier", letter)
        id_to_letter[raw_id] = letter
        opt_text, opt_imgs = _extract_text_and_images(choice, root_dir)
        # QTI ``fixed="true"`` pins this choice to its position even when the
        # interaction is shuffled (e.g. "Tất cả đáp án trên").
        options.append({
            "id": letter, "text": opt_text, "images": opt_imgs,
            "fixed": choice.attrib.get("fixed") == "true",
        })

    # Correct answer. QTI 3.0: qti-response-declaration→qti-correct-response→qti-value.
    # QTI 2.1:  responseDeclaration→correctResponse→value. Tìm correctResponse trước
    # rồi lấy value bên trong để không nhầm với defaultValue/value của outcome.
    correct: str | None = None
    for resp_decl in _findall(root, *_TAG_RESP_DECL):
        if resp_decl.attrib.get("identifier") != response_id:
            continue
        cr = _find(resp_decl, *_TAG_CORRECT)
        value_el = _find(cr, *_TAG_VALUE) if cr is not None else None
        if value_el is not None and value_el.text:
            raw = value_el.text.strip()
            correct = id_to_letter.get(raw, raw if raw in _OPTION_IDS else None)
            break
    if correct is None:
        raise QtiLoadError(f"Câu hỏi thiếu đáp án đúng: {item_path}")

    return {
        "id": str(uuid.uuid4()),
        # Mã câu hỏi gốc do nhà cung cấp đặt (identifier của qti-assessment-item,
        # vd "111101"). Hiển thị ở dòng "Mã câu hỏi" trong báo cáo (sheet Đáp án).
        "code": root.attrib.get("identifier") or "",
        "text": text,
        "images": images,
        # Khối có thứ tự (chữ ↔ ảnh xen kẽ) để render đúng vị trí ảnh (AD-98).
        # Khối ảnh mang ``index`` trỏ vào ``images``. Payload cũ không có → FE tự
        # lùi về hiển thị text rồi images (tương thích ngược).
        "blocks": blocks,
        "options": options,
        "correct_option": correct,
        "order_index": order_index,
        "_shuffle_options_hint": shuffle_options,
    }


def load_qti_package(root_dir: str) -> dict:
    """Parse a QTI package (3.0 hoặc 2.1) rooted at ``root_dir`` (a directory
    containing imsmanifest.xml).  Returns ``{"exam": {...}, "payload": {...}}``
    ready to be encrypted+stored via the existing exam_package flow."""
    manifest_path = os.path.join(root_dir, "imsmanifest.xml")
    if not os.path.isfile(manifest_path):
        raise QtiLoadError("Không tìm thấy imsmanifest.xml trong gói QTI.")
    manifest = _safe_parse_root(manifest_path, "imsmanifest.xml")

    # Find the test resource. Type = ``imsqti_test_xmlv3p0`` (3.0) hoặc
    # ``imsqti_test_xmlv2p1`` (2.1) → khớp tiền tố chung ``imsqti_test_xml``.
    test_href: str | None = None
    for res in _findall(manifest, "resource"):
        if (res.attrib.get("type") or "").startswith("imsqti_test_xml"):
            test_href = res.attrib.get("href")
            break
    if not test_href:
        raise QtiLoadError("Gói QTI không có file assessment-test.")

    test_path = os.path.join(root_dir, test_href)
    if not os.path.isfile(test_path):
        raise QtiLoadError(f"Không tìm thấy file test: {test_href}")
    test_root = _safe_parse_root(test_path, f"file test {test_href}")

    exam_name = test_root.attrib.get("title") or "QTI Exam"
    # Optional duration via time-limits max-time (3.0) / maxTime (2.1), giây.
    duration_minutes: int | None = None
    tl = _find(test_root, *_TAG_TIME_LIMITS)
    if tl is not None:
        max_time = _attr(tl, "max-time", "maxTime")
        if max_time:
            try:
                duration_minutes = max(1, int(float(max_time) / 60))
            except ValueError:
                duration_minutes = None
    # Đảo câu (mặc định TẮT, do nhà cung cấp quyết — AD-34). Bật khi:
    #  * QTI 3.0/2.1: phần tử ``<qti-ordering shuffle="true">`` / ``<ordering shuffle="true">``
    #  * QTI 2.1 (biến thể của nhà cung cấp): thuộc tính ``ordering="random"`` trên section.
    shuffle_questions = False
    ordering = _find(test_root, *_TAG_ORDERING)
    if ordering is not None:
        shuffle_questions = ordering.attrib.get("shuffle") == "true"
    if not shuffle_questions:
        for sec in _findall(test_root, *_TAG_SECTION):
            if sec.attrib.get("ordering") == "random":
                shuffle_questions = True
                break

    # selection (qti-selection 3.0 / selection 2.1) chọn ngẫu nhiên MỘT PHẦN câu
    # hỏi mỗi lần lắp đề. Model của ta nạp 1 payload cố định cho mọi thí sinh nên
    # không thể trung thực → báo lỗi rõ thay vì âm thầm giao đủ (sai đề).
    if _find(test_root, *_TAG_SELECTION) is not None:
        raise QtiLoadError(
            "Gói QTI dùng selection (chọn ngẫu nhiên một phần câu hỏi) — "
            "hệ thống chưa hỗ trợ. Vui lòng xuất đề đầy đủ, không dùng selection."
        )

    # Ordered item refs.
    item_refs = _findall(test_root, *_TAG_ITEM_REF)
    if not item_refs:
        raise QtiLoadError("Test không có câu hỏi nào (assessment-item-ref).")

    questions: list[dict] = []
    any_shuffle_opts = False
    for idx, ref in enumerate(item_refs):
        href = ref.attrib.get("href")
        if not href:
            continue
        item_path = os.path.normpath(os.path.join(os.path.dirname(test_path), href))
        # If the href is relative to package root instead of test dir, fall back.
        if not os.path.isfile(item_path):
            alt = os.path.normpath(os.path.join(root_dir, href))
            if os.path.isfile(alt):
                item_path = alt
            else:
                raise QtiLoadError(f"Không tìm thấy file câu hỏi: {href}")
        q = _parse_item(item_path, root_dir, order_index=idx)
        # QTI ``fixed="true"`` on an item-ref pins the question's position even
        # when section ordering is shuffled.
        q["fixed"] = ref.attrib.get("fixed") == "true"
        if q.pop("_shuffle_options_hint", False):
            any_shuffle_opts = True
        questions.append(q)

    return {
        "exam": {
            "name": exam_name,
            "duration_minutes": duration_minutes,  # may be None — caller will fill
            "exam_date": None,
            "shuffle_questions": shuffle_questions,
            "shuffle_options": any_shuffle_opts,
        },
        "payload": {"questions": questions},
    }
