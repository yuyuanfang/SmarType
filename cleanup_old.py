"""清理舊的 SmarType 進程，由 start.bat 呼叫"""
import psutil, ctypes, os, sys

k32 = ctypes.windll.kernel32
current_pid = os.getpid()

for p in psutil.process_iter(['pid', 'cmdline']):
    try:
        cmd = ' '.join(p.info['cmdline'] or [])
        pid = p.info['pid']
        if pid == current_pid:
            continue
        if 'dictation.py' in cmd or 'dashboard.py' in cmd:
            h = k32.OpenProcess(1, False, pid)
            if h:
                k32.TerminateProcess(h, 0)
                k32.CloseHandle(h)
    except Exception:
        pass
