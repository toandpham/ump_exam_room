"""Exam run-control + monitoring (AD-47).

Control is keyed by SITTING (buổi thi): distribute / start / extend / end act on a
sitting's sessions. Timers are per-candidate; pause/resume act on a single
session and may be issued by the chủ tịch (any session of an owned exam) or a
giám thị (only sessions of candidates in their room). The cohort-wide "Hết giờ
làm bài" button is gone — each candidate auto-submits when their own clock hits 0
(background sweep in main.py).

Router được tách thành 3 submodule (control / sessions / listings) rồi gộp lại
qua ``router`` để giữ nguyên public surface (main.py include 1 router duy nhất).
"""

from fastapi import APIRouter

from . import control, listings, sessions

router = APIRouter()
router.include_router(control.router)
router.include_router(sessions.router)
router.include_router(listings.router)
