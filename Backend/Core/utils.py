from datetime import datetime, timezone
import subprocess # for chaffa image rendering
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

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


def renderImage(path: str, width: int = 80, height: int = 40):
    imagePath = PROJECT_ROOT / path

    if not imagePath.is_file():
        print(f"❌ Image not found: {imagePath}")
        return False

    try:
        subprocess.run(
            [
                "chafa",
                "--size", f"{width}x{height}",
                "--colors", "full",
                "--symbols", "all",
                str(imagePath)
            ],
            check=True
        )
        return True

    except FileNotFoundError:
        print("❌ Chafa is not installed.")
        return False

    except subprocess.CalledProcessError as e:
        print(f"❌ Chafa failed: {e}")
        return False