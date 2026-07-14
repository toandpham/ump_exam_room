/* keyblocker.exe — low-level keyboard hook (WH_KEYBOARD_LL) for the Exam Kiosk.
 *
 * Electron / browser user-mode code CANNOT swallow OS-reserved combos (the
 * Windows key, Alt+Tab, Alt+Esc, Ctrl+Esc). A global low-level keyboard hook
 * runs before the system dispatches the key, so it CAN block them. (Only
 * Ctrl+Alt+Del — the Secure Attention Sequence — is unblockable; even SEB
 * cannot stop that without a driver.)
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
static DWORD  g_parent;

static LRESULT CALLBACK kbProc(int nCode, WPARAM wParam, LPARAM lParam) {
    if (nCode == HC_ACTION && (wParam == WM_KEYDOWN || wParam == WM_SYSKEYDOWN)) {
        KBDLLHOOKSTRUCT *k = (KBDLLHOOKSTRUCT *)lParam;
        DWORD vk  = k->vkCode;
        BOOL  alt  = (k->flags & LLKHF_ALTDOWN) != 0;
        BOOL  ctrl = (GetAsyncKeyState(VK_CONTROL) & 0x8000) != 0;

        if (vk == VK_LWIN || vk == VK_RWIN) return 1;          /* phím Windows */
        if (alt  && (vk == VK_TAB || vk == VK_ESCAPE || vk == VK_F4)) return 1; /* Alt+Tab/Esc/F4 */
        if (ctrl && vk == VK_ESCAPE) return 1;                  /* Ctrl+Esc = Start */
        if (vk == VK_APPS) return 1;                            /* phím menu ngữ cảnh */
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
    g_hook = SetWindowsHookEx(WH_KEYBOARD_LL, kbProc, GetModuleHandle(NULL), 0);
    if (!g_hook) return 1;
    SetTimer(NULL, 1, 1000, watchParent);
    MSG msg;
    while (GetMessage(&msg, NULL, 0, 0) > 0) { TranslateMessage(&msg); DispatchMessage(&msg); }
    UnhookWindowsHookEx(g_hook);
    return 0;
}
