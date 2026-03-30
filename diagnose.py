import sys
print("step 1: Python OK", sys.version)

try:
    import tkinter as tk
    print("step 2: tkinter OK")
except Exception as e:
    print("step 2 FAIL:", e)

try:
    from PIL import Image, ImageDraw
    print("step 3: PIL OK")
except Exception as e:
    print("step 3 FAIL:", e)

try:
    import pystray
    print("step 4: pystray OK")
except Exception as e:
    print("step 4 FAIL:", e)

try:
    import pyaudio
    print("step 5: pyaudio OK")
except Exception as e:
    print("step 5 FAIL:", e)

try:
    import keyboard
    print("step 6: keyboard OK")
except Exception as e:
    print("step 6 FAIL:", e)

try:
    from groq import Groq
    print("step 7: groq OK")
except Exception as e:
    print("step 7 FAIL:", e)

try:
    import pyperclip
    import pyautogui
    print("step 8: pyperclip/pyautogui OK")
except Exception as e:
    print("step 8 FAIL:", e)

try:
    from window_detector import get_active_window_info
    print("step 9: window_detector OK")
except Exception as e:
    print("step 9 FAIL:", e)

try:
    from converter import convert
    print("step 10: converter OK")
except Exception as e:
    print("step 10 FAIL:", e)

print("\nALL DONE")
input("Press Enter to exit...")
