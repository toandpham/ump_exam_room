"""AD-90: lệnh tra cứu phiên thi của một thí sinh (dùng khi tranh cãi 'đã nộp chưa')."""

import pytest

from app.check_candidate import _run

pytestmark = pytest.mark.asyncio

QUESTIONS = [{"text": "1+1?", "correct": "A", "options": ["A", "B", "C", "D"]}]


async def test_prints_every_session_of_the_candidate(factory, capsys):
    exam, sitting, _ = await factory.active_exam(QUESTIONS)
    cand = await factory.candidate(exam.id)

    assert await _run(cand.cccd) == 0
    out = capsys.readouterr().out
    assert cand.cccd in out
    assert exam.name in out
    assert "KHÔNG có phiên nào" in out      # chưa xác nhận buổi nào


async def test_unknown_identifier_reports_clearly(capsys):
    assert await _run("999999999999") == 1
    assert "Không có thí sinh nào" in capsys.readouterr().out
