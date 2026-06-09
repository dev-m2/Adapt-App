from datetime import datetime, timezone



# for renderImage() and compilation
import os
import shutil
import chafa
from chafa.loader import Loader

import sys
from pathlib import Path

if getattr(sys, 'frozen', False):
    base_path = Path(sys._MEIPASS)
else:
    base_path = Path(__file__).resolve().parent.parent.parent

PROJECT_ROOT = base_path
NEURO_MODS_DIR = PROJECT_ROOT / "NeuroMods"

def renderImage(relative_path: str | Path, max_width: int = 80):
    """
    Print an image from PROJECT_ROOT to the terminal.
    Example: renderImage("NeuroMods/myimage.png")
    """
    image_path = PROJECT_ROOT / relative_path
    
    if not image_path.exists():
        print(f"Warning: Image not found → {image_path}")
        return
    
    image = Loader(str(image_path))
    
    term_width = shutil.get_terminal_size().columns
    canvas_width = min(term_width - 2, max_width)
    aspect_ratio = image.height / image.width
    
    canvas_height = max(1, int(canvas_width * aspect_ratio * 0.5))
    
    config = chafa.CanvasConfig()
    config.width = canvas_width
    config.height = canvas_height
    
    canvas = chafa.Canvas(config)
    canvas.draw_all_pixels(
        image.pixel_type,
        image.get_pixels(),
        image.width,
        image.height,
        image.rowstride
    )
    print(canvas.print().decode())

def inputCode(opening_text = ""):
    if opening_text:
        print(opening_text) 
    print("When finished, type '!END' on a new line and press enter.\n")

    lines = []
    while True:
        try:
            line = input()
            if line.strip() == '!END':
                break
            else:
                lines.append(line)
    
        except EOFError: # End Of File errors
            break
    
    return '\n'.join(lines) # joins into one string

# All 3 for createAdaptation(), as starting points
CONTENT_EMPTY = {
        "cue": None, "response": None, "type": None,
        "code": None, "baseline": None, "target": None,
        "netDirection": None, "units": None
    }

SCHEDULING_DEFAULT = {
    "S": 0.0,
    "D": None,
    "R": None,
    "tauG": 7.0,
    "state": 1,
    "step": 0,
    "lastReview": None,
    "exertion": 0
}

def STATE_DEFAULT():
    return {
        "peakFitness": 0,
        "peakFitnessDate": datetime.now(timezone.utc).isoformat(), # ISO-8601 standard string
        "fitness": 0,
        "fatigue": 0,
    }


# PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


# def renderImage(path: str, width: int = 80, height: int = 40):
#     imagePath = PROJECT_ROOT / path

#     if not imagePath.is_file():
#         print(f"❌ Image not found: {imagePath}")
#         return False

#     try:
#         subprocess.run(
#             [
#                 "chafa",
#                 "--size", f"{width}x{height}",
#                 "--colors", "full",
#                 "--symbols", "all",
#                 str(imagePath)
#             ],
#             check=True
#         )
#         return True

#     except FileNotFoundError:
#         print("❌ Chafa is not installed.")
#         return False

#     except subprocess.CalledProcessError as e:
#         print(f"❌ Chafa failed: {e}")
#         return False


# def renderImage(relative_path: str | Path, max_width: int = 80):
#     """
#     Print an image from PROJECT_ROOT to the terminal.

#     Example:
#         print_image("assets/flags/gb.svg")
#     """

#     image_path = PROJECT_ROOT / relative_path

#     image = Loader(str(image_path))

#     term_width = shutil.get_terminal_size().columns
#     canvas_width = min(term_width - 2, max_width)

#     aspect_ratio = image.height / image.width

#     # Terminal characters are taller than they are wide
#     canvas_height = max(
#         1,
#         int(canvas_width * aspect_ratio * 0.5)
#     )

#     config = chafa.CanvasConfig()
#     config.width = canvas_width
#     config.height = canvas_height

#     canvas = chafa.Canvas(config)

#     canvas.draw_all_pixels(
#         image.pixel_type,
#         image.get_pixels(),
#         image.width,
#         image.height,
#         image.rowstride
#     )

#     print(canvas.print().decode())

# renderImage("NeuroMods/Flags/Countries/aq.svg")
# in the future, make it take the NM name (stored in source), and the Path seperately, so that less is stored in the path key:value;