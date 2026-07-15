# Hệ thống thi trắc nghiệm web offline

## Cập nhật

Máy chủ **tự động cập nhật** khi có bản vá mới — không cần làm gì.

- Chạy lúc **02:15 và 03:15** hằng đêm.
- **Chỉ cập nhật khi chắc chắn không đụng kỳ thi**: không thí sinh nào đang trong
  phiên (kể cả mới đăng nhập), không buổi thi đang mở, và không kỳ thi/buổi thi nào
  trong vòng 1 ngày.
- **Luôn sao lưu CSDL trước**; nếu cập nhật hỏng thì **tự quay về bản cũ** + phục hồi.
- Nhật ký: `logs/auto-update.log`

```bash
./update.sh                                    # cập nhật NGAY (không chờ ban đêm)
tail -f logs/auto-update.log                   # xem nó đã làm gì / vì sao bỏ qua
sudo systemctl disable --now exam-autoupdate.timer   # tắt tự động cập nhật
```
