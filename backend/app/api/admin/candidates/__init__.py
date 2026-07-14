"""Candidate management (admin): whitelist CRUD, bulk import, photos, lock, emergency add.

AD-75: tách từ file candidates.py 641 dòng thành package (như monitor/ ở AD-69):
``_common`` (helpers dùng chung) + ``importing`` (template/import/photos ZIP) +
``manage`` (assign/stats/export/emergency-add/CRUD đơn lẻ), gộp lại qua ``router``
để giữ nguyên public surface (main.py include 1 router duy nhất).

THỨ TỰ include quan trọng: ``importing`` trước ``manage`` để các path cụ thể
(/template.xlsx, /import/*, /photos/zip) đăng ký TRƯỚC route động /{candidate_id}.
"""

from fastapi import APIRouter

from . import importing, manage

router = APIRouter()
router.include_router(importing.router)
# manage có 2 route path "" (POST/GET create+list — giữ nguyên như file cũ);
# FastAPI cấm include_router khi cả prefix lẫn path đều rỗng → nối thẳng routes.
# Router cha không có dependencies/tags riêng nên tương đương include_router;
# prefix + dependencies thật được main.py áp khi include vào app như trước.
router.routes.extend(manage.router.routes)
