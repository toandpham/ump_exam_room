# shellcheck shell=bash
# Chạy git theo ĐÚNG CHỦ SỞ HỮU repo — dùng chung bởi update.sh + update-watcher.sh
# (gộp ở refactor đợt 3; trước đây 2 bản gần y hệt, sửa một bên quên bên kia).
#
# Vì sao cần: watcher chạy dưới systemd (thường là root) nhưng repo thuộc user
# thường → git chạy bằng root sẽ dùng SAI khoá SSH khi pull và làm lệch quyền file
# trong .git. `sudo -u <owner>` giữ đúng danh tính; `safe.directory` để git không
# từ chối repo "của người khác".
#
# Dùng: source "$(dirname "$0")/scripts/lib/git.sh" "$REPO_DIR"  → có hàm run_git.

_GIT_REPO_DIR="${1:-$PWD}"
GIT_OWNER=$(ls -ld "$_GIT_REPO_DIR/.git" 2>/dev/null | awk '{print $3}')
GIT_ME=$(id -un)

run_git() {
  if [ -n "$GIT_OWNER" ] && [ "$GIT_ME" != "$GIT_OWNER" ] && command -v sudo >/dev/null 2>&1; then
    sudo -u "$GIT_OWNER" git "$@"
  else
    git "$@"
  fi
}

git config --global --add safe.directory "$_GIT_REPO_DIR" >/dev/null 2>&1 || true
