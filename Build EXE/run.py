"""Run JLmain from editable source files."""
import os
import sys


base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, base)
try:
    os.chdir(base)
except Exception:
    pass

# Keep heavy imports visible to PyInstaller.
import cv2  # noqa: F401,E402
import customtkinter  # noqa: F401,E402
import keyboard  # noqa: F401,E402
import numpy  # noqa: F401,E402
import tkinter  # noqa: F401,E402
import tkinter.filedialog  # noqa: F401,E402
import tkinter.messagebox  # noqa: F401,E402
import tkinter.scrolledtext  # noqa: F401,E402
import tkinter.ttk  # noqa: F401,E402

try:
    import cryptography  # noqa: F401,E402
except Exception:
    pass


if "--premium-worker" in sys.argv:
    import premium_worker  # noqa: E402

    premium_worker.main()
else:
    import JLmain  # noqa: E402

    JLmain.main()
