"""Auth thí sinh: đăng nhập whitelist, đăng ký tại chỗ, xác nhận/báo sai thông tin.

Refactor đợt 3: tách từ auth.py 513 dòng thành package (pattern candidates/ AD-75):
``_common`` (helpers + _session_state) + ``login`` + ``register`` + ``info``, gộp
lại qua ``router`` để giữ nguyên public surface (main.py include 1 router).

``_session_state`` re-export vì api/exam/session.py import từ đây."""

from fastapi import APIRouter

from . import info, login, register
from ._common import _session_state  # noqa: F401 — api/exam/session.py dùng

router = APIRouter()
router.include_router(login.router)
router.include_router(register.router)
router.include_router(info.router)
