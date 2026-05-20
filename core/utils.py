from datetime import datetime, timezone

def codeInput(openingText = ""):
    if openingText: # checks if it's not empty
        print(openingText) 
    print("When finished, type '!END' on a new line and press enter.\n")

    lines = []
    while True:
        try:
            line = input()
            if line.strip().upper() == '!END':
                break
            else:
                lines.append(line)
        except EOFError: # 'end of file' errors
            break
    
    return '\n'.join(lines) # joins into one string

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

def stateDefault():
    return {
        "peakFitness": 0,
        "peakFitnessDate": datetime.now(timezone.utc).isoformat(),
        "fitness": 0,
        "fatigue": 0,
    }

