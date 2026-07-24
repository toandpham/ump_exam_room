/* keyblocker.exe — low-level keyboard hook (WH_KEYBOARD_LL) for the Exam Kiosk.
 *
 * Electron / browser user-mode code CANNOT swallow OS-reserved combos (the
 * Windows key, Alt+Tab, Alt+Esc, Ctrl+Esc). A global low-level keyboard hook
 * runs before the system dispatches the key, so it CAN block them. (Only
 * Ctrl+Alt+Del — the Secure Attention Sequence — is unblockable; even SEB
 * cannot stop that without a driver.)
 *
 * HIỆU NĂNG (AD-104, vá lag máy yếu): hook LL là "trạm kiểm soát" mà MỌI phím
 * của cả Windows phải đi qua — callback này chạy trên message loop của CHÍNH
 * tiến trình này. Máy yếu mà tiến trình bị CPU bỏ đói thì mỗi phím phải chờ nó
 * thức dậy → trễ hàng giây. Hai biện pháp:
 *   1. Nâng ưu tiên: HIGH_PRIORITY_CLASS + thread THREAD_PRIORITY_HIGHEST —
 *      Windows luôn đánh thức trạm ngay khi có phím. An toàn vì tiến trình chỉ
 *      làm đúng một việc tí hon.
 *   2. Đường nóng tối giản: BỎ GetAsyncKeyState (một cú hỏi trạng thái mỗi
 *      phím); tự theo dõi Ctrl từ chính luồng sự kiện (down/up của L/RCONTROL).
 *      Callback giờ chỉ còn vài phép so sánh số nguyên.
 *
 * Usage: keyblocker.exe <parentPid>
 *   - installs the hook and runs a message loop
 *   - exits automatically when the parent process (the kiosk) dies, so keys
 *     are never left blocked if the kiosk crashes
 *
 * Cross-compiled on macOS:
 *   i686-w64-mingw32-gcc keyblocker.c -o keyblocker.exe -mwindows -O2 -s
 */
#include <windows.h>
#include <stdlib.h>

static HHOOK g_hook;
static DWORD g_parent;
/* Trạng thái Ctrl theo dõi từ luồng phím (bit0 = LCtrl, bit1 = RCtrl) —
 * thay cho GetAsyncKeyState trên đường nóng. */
static DWORD g_ctrl;

static LRESULT CALLBACK kbProc(int nCode, WPARAM wParam, LPARAM lParam) {
    if (nCode == HC_ACTION) {
        const KBDLLHOOKSTRUCT *k = (const KBDLLHOOKSTRUCT *)lParam;
        DWORD vk   = k->vkCode;
        BOOL  down = (wParam == WM_KEYDOWN || wParam == WM_SYSKEYDOWN);

        /* Theo dõi Ctrl (cả down lẫn up) rồi cho qua ngay. */
        if (vk == VK_LCONTROL || vk == VK_RCONTROL || vk == VK_CONTROL) {
            DWORD bit = (vk == VK_RCONTROL) ? 2u : 1u;
            if (down) g_ctrl |= bit; else g_ctrl &= ~bit;
            return CallNextHookEx(g_hook, nCode, wParam, lParam);
        }

        if (down) {
            if (vk == VK_LWIN || vk == VK_RWIN) return 1;      /* phím Windows */
            if ((k->flags & LLKHF_ALTDOWN) &&
                (vk == VK_TAB || vk == VK_ESCAPE || vk == VK_F4)) return 1; /* Alt+Tab/Esc/F4 */
            if (g_ctrl && vk == VK_ESCAPE) return 1;            /* Ctrl+Esc = Start */
            if (vk == VK_APPS) return 1;                        /* phím menu ngữ cảnh */
        }
    }
    return CallNextHookEx(g_hook, nCode, wParam, lParam);
}

static VOID CALLBACK watchParent(HWND h, UINT m, UINT_PTR id, DWORD t) {
    (void)h; (void)m; (void)id; (void)t;
    if (!g_parent) return;
    HANDLE p = OpenProcess(SYNCHRONIZE, FALSE, g_parent);
    if (!p) { PostQuitMessage(0); return; }                    /* parent gone */
    if (WaitForSingleObject(p, 0) == WAIT_OBJECT_0) { CloseHandle(p); PostQuitMessage(0); return; }
    CloseHandle(p);
}

int WINAPI WinMain(HINSTANCE hi, HINSTANCE hp, LPSTR cmd, int show) {
    (void)hi; (void)hp; (void)show;
    g_parent = (cmd && *cmd) ? (DWORD)atoi(cmd) : 0;

    /* AD-104: trạm kiểm soát phím phải luôn được đánh thức NGAY — kể cả khi máy
     * yếu đang quá tải. (Không dùng REALTIME: cao hơn nữa là rủi ro hệ thống.) */
    SetPriorityClass(GetCurrentProcess(), HIGH_PRIORITY_CLASS);
    SetThreadPriority(GetCurrentThread(), THREAD_PRIORITY_HIGHEST);

    /* Mồi trạng thái Ctrl MỘT LẦN lúc khởi động (lỡ Ctrl đang được giữ sẵn);
     * từ đây trở đi chỉ theo dõi qua luồng phím, không hỏi lại. */
    if (GetAsyncKeyState(VK_LCONTROL) & 0x8000) g_ctrl |= 1u;
    if (GetAsyncKeyState(VK_RCONTROL) & 0x8000) g_ctrl |= 2u;

    g_hook = SetWindowsHookEx(WH_KEYBOARD_LL, kbProc, GetModuleHandle(NULL), 0);
    if (!g_hook) return 1;
    SetTimer(NULL, 1, 1000, watchParent);
    MSG msg;
    while (GetMessage(&msg, NULL, 0, 0) > 0) { TranslateMessage(&msg); DispatchMessage(&msg); }
    UnhookWindowsHookEx(g_hook);
    return 0;
}
