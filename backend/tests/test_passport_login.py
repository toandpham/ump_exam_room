"""Passport login + Excel passport classification (AD-58)."""
import uuid

import pytest

from app.services import excel_service


@pytest.mark.asyncio
async def test_passport_candidate_can_login(client, factory):
    # Unique passport per run so re-runs on the dev DB don't collide (AD-55).
    pp = "P" + uuid.uuid4().hex[:7].upper()
    exam, sitting, _ = await factory.active_exam([{"text": "q1", "correct": "A"}])
    await factory.candidate(exam.id, cccd=pp, id_type="passport")

    # Lowercase input is normalized to the stored uppercase value.
    r = await client.post("/api/exam/auth/login", json={"cccd": pp.lower()})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["token"]
    assert body["candidate"]["id_type"] == "passport"
    assert body["candidate"]["cccd"] == pp


@pytest.mark.asyncio
async def test_cccd_candidate_still_logs_in(client, factory):
    exam, sitting, _ = await factory.active_exam([{"text": "q1", "correct": "A"}])
    cand = await factory.candidate(exam.id)   # factory generates a unique 12-digit CCCD
    r = await client.post("/api/exam/auth/login", json={"cccd": cand.cccd})
    assert r.status_code == 200, r.text
    assert r.json()["candidate"]["id_type"] == "cccd"


@pytest.mark.asyncio
async def test_invalid_identifier_rejected(client, factory):
    await factory.active_exam([{"text": "q1", "correct": "A"}])
    for bad in ("12345", "07909500011", "AB-12"):
        r = await client.post("/api/exam/auth/login", json={"cccd": bad})
        assert r.status_code == 400, f"{bad!r} -> {r.status_code}"


def test_excel_validate_row_classifies_passport():
    row = ("C1234567", "John Smith", "1990-08-15", "Đơn vị B",
           2015, "Y đa khoa", "Đối tượng 2", 1, "Phòng 1")
    data, errors = excel_service.validate_row(row)
    assert errors == []
    assert data["id_type"] == "passport"
    assert data["cccd"] == "C1234567"


def test_excel_validate_row_classifies_cccd():
    row = ("079095000111", "Nguyễn Văn An", "1995-03-12", "Đơn vị A",
           2017, "Y đa khoa", "Bác sĩ", 1, "Phòng 1")
    data, errors = excel_service.validate_row(row)
    assert errors == []
    assert data["id_type"] == "cccd"
