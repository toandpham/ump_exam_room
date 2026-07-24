"""AD-90: thu nhỏ ảnh đề quá khổ để máy thi yếu (Win7/4GB) đỡ tốn RAM + băng thông."""

import io

from PIL import Image

from app.services import exam_assets


def _jpeg(width: int, height: int) -> bytes:
    im = Image.new("RGB", (width, height), (120, 40, 200))
    # Nhiễu nhẹ cho ảnh không nén được xuống mức phi thực tế.
    for x in range(0, width, 7):
        for y in range(0, height, 11):
            im.putpixel((x, y), (x % 255, y % 255, 30))
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=95)
    return buf.getvalue()


def test_large_image_is_downscaled_to_max_width():
    original = _jpeg(3200, 2400)
    out, mime = exam_assets.shrink_image(original, "image/jpeg")
    with Image.open(io.BytesIO(out)) as im:
        assert im.width == exam_assets.MAX_IMAGE_WIDTH
        # Giữ đúng tỉ lệ 4:3 theo trần hiện hành (AD-109: 1280 → 960).
        assert im.height == round(exam_assets.MAX_IMAGE_WIDTH * 2400 / 3200)
    assert len(out) < len(original)
    assert mime == "image/jpeg"


def test_small_image_is_returned_untouched():
    original = _jpeg(800, 600)
    out, _ = exam_assets.shrink_image(original, "image/jpeg")
    assert out is original


def test_corrupt_image_is_returned_untouched():
    junk = b"not an image at all"
    out, mime = exam_assets.shrink_image(junk, "image/jpeg")
    assert out == junk and mime == "image/jpeg"
