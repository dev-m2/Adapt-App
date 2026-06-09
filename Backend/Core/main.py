from db import *
from utils import inputCode, renderImage
from scheduler import schedulerReview
from pathlib import Path # for importNeuroMods()
import pandas as pd # for importNeuroMods()
from textwrap import dedent # for getting a grade
from datetime import datetime, timezone # for reviewAdaptations()

# For PyInstaller???
import sys
import os
from pathlib import Path
from utils import NEURO_MODS_DIR, PROJECT_ROOT   # <-- Import the constants

print(NEURO_MODS_DIR)


def init():
    initDB() # initializes database


def createAdaptation():
    typeInput = input("What is the adaptation's type? (1 Text; 2 Python Code; 3 Run): ").strip().lower()

    content = CONTENT_EMPTY.copy() # uses utils constant

    match typeInput:
        case "1" | "text" | "":
            content["cue"] = input("What is the cue?: ")
            content["response"] = input("What is the response?: ")
            content["type"] = "text"
        
        case "2" | "py" | "python" | "python code":
            content["code"] = inputCode("Provide the Python code: ")
            content["type"] = "python"
        
        case "3" | "run":
            content["cue"] = input("What is the distance?: ")
            content["target"] = input("What is your target time (in seconds)?: ")
            content["baseline"] = input("What is the baseline time of an untrained person?: ")
            content["netDirection"] = "negative"
            content["type"] = "run"
            content["units"] = "s"

        case _:
            print("Faulty input!")
            return
    
    updateDB(content_dict = content)


def viewAdaptations(option: int = 1):
    def _view():
        print(df.to_string(max_colwidth=50), "\n")
    
    df = dbDataFrame()

    if option == 0: # view only
        _view()
        return

    while True:
        if df.empty:
            print("You have no adaptations!")
            break
        else:
            _view()

        print("Options: 0 Exit; 1 View Full; 2 Delete;\n")
        choice = input("Choice: ").strip()

        match choice:
            case "1":
                adaptId = input("Which adaptation do you want to view fully?: ").strip()
                with pd.option_context('display.max_colwidth', None, 'display.width', None):
                    print(df.loc[adaptId])
                input("Continue?")

            case "2":
                adaptId = input("Delete which adaptation? (Enter ID or type ALL): ").strip()

                if adaptId == "ALL":
                    confirm = input("⚠️  REALLY delete ALL cards? This cannot be undone! (y/n): ").strip().lower()
                    if confirm != "y":
                        print("Delete cancelled.")
                        break
                
                deleteAdaptation(adaptId) # deletes when ALL check passes

            case _: 
                break         


def reviewAdaptations():
    def _review(adapt_id: str) -> bool:
        # Queries card data
        fullData, content, adaptType = getAdaptData(adapt_id)
        
        # id validity check
        if not fullData: 
            print("Adaptation not found.")
            return False
        
        # Hard coded reviewing
        match adaptType:
            case "text":
                print(f"Cue: {content.get('cue')}")
                input("Your answer: ")
                print(f"Response: {content.get('response')}")
            
            case "image-text":
                renderImage(content.get('path'))
                print(content.get('cue'))
                answer = input("Answer: ")
                print(f"Response: {content.get('response')}")

            case "run":
                print(content.get('cue'))
                input("Press Enter when you get back...")
                input("What was your time (mm:ss): ")

            case _:
                print("Unknown adaptation type.")
                return False
        
        # Asks for rating
        rating = input(dedent("""
            Again (1)  Hard (2)  Good (3)  Easy (4)
            How well did you do?: """)).strip().lower()

        if   rating in ("1", "again"): grade = 1
        elif rating in ("2", "hard"):  grade = 2
        elif rating in ("3", "good"):  grade = 3
        elif rating in ("4", "easy"):  grade = 4
        else:
            print("Invalid input! Skipping.")
            return False
        
        # Updates scheduling & due
        schedulingDict, due = schedulerReview(fullData, grade=grade)

        # Saves everything
        updateDB(
            adapt_id=adapt_id,
            scheduling_dict=schedulingDict,
            newDue=due
            )

        print("✅ Review saved.")
        return True # successful review
    

    # Review Process
    while True:
        df = dbDataFrame()
        dueCards = df[df['due'] <= datetime.now(timezone.utc).isoformat()]

        if dueCards.empty:
            print("\nNo cards are due right now!")
            break

        print(f"\nStarting review round — {len(dueCards)} card(s) due.\n")

        row = dueCards.sample(n=1) # random row (as DataFrame)
        adapt_id = row.index[0]

        _review(adapt_id=adapt_id) # reviews it

        if len(dueCards) == 1: # checks if only 1 was due
            print("You've reviewed all due cards!")
            break
        
        if input("\nReview another round? (Y/n): ").strip().lower() == "n":
            print("Good reviewing!")
            break
        

# def importNeuroMod():
#     Location = Path("../../NeuroMods")    # creates Path object
#     nmList = list(Location.rglob("*.nm")) # list of Path objects

#     if nmList:
#         print("Available NeuroMods:")
#         for i, file in enumerate(nmList):
#             print(f"{i} {file.name}") # prints index and name
#     else: 
#         print("No NeuroMods found!") # if empty
#         return

#     try:
#         choice = int(input("\nWhich one would you like to import (index)?: "))
#         chosenFile = nmList[choice]
#     except (ValueError, IndexError):
#         print("Invalid selection!")
#         return
    
#     # last safety check, might not be necessary due to above try
#     if not chosenFile.is_file():
#         print("That is not a valid NeuroMod!")
#         return
    
#     df = pd.read_csv(chosenFile)
#     df["content"] = df["content"].apply(json.loads) # necessary, or else there'll be excessive "
#     for _, row in df.iterrows():
#         updateDB(
#             content_dict=row["content"],
#             source=row["source"]
#         )
    
#     viewAdaptations(option=0)

def importNeuroMod():
    """Import a .nm file from the NeuroMods folder."""
    
    if not NEURO_MODS_DIR.exists():
        print(f"Error: NeuroMods folder not found at:\n{NEURO_MODS_DIR}")
        print("Make sure the 'NeuroMods' folder is next to the executable.")
        return

    nmList = list(NEURO_MODS_DIR.rglob("*.nm"))
    
    if not nmList:
        print("No .nm files found in the NeuroMods folder!")
        return

    print("Available NeuroMods:")
    for i, file in enumerate(nmList):
        print(f"{i}  {file.name}")

    try:
        choice = int(input("\nWhich one would you like to import (index)?: "))
        chosenFile = nmList[choice]
    except (ValueError, IndexError):
        print("Invalid selection!")
        return

    if not chosenFile.is_file():
        print("That is not a valid NeuroMod file!")
        return

    try:
        df = pd.read_csv(chosenFile)
        df["content"] = df["content"].apply(json.loads)

        print(f"Importing {chosenFile.name} ...")
        
        for _, row in df.iterrows():
            updateDB(
                content_dict=row["content"],
                source=row["source"]
            )
        
        print("Import completed successfully!")
        viewAdaptations(option=0)
        
    except Exception as e:
        print(f"Error importing file: {e}")

def main():
    while True:
        n = dueCount()
        print("\n")
        print("=========================================================")
        print("                 Welcome to the Adapt App")
        print("=========================================================")
        print(f"Options: 0 Exit; 1 Create; 2 View; 3 Review ({n}); 4 Import;\n")

        choice = input("Choice: ").strip()

        match choice:
            case "0" | "":
                print("Goodbye!")
                break
            case "1":
                createAdaptation()
            case "2":
                viewAdaptations()
            case "3":
                 reviewAdaptations()
            case "4":
                importNeuroMod()
            case "999":
                _test()
            case _:
                print("Invalid input!")

def _test():
    print("YOU'VE TRIGGERED A TESTING FUNCTION!")
    renderImage("NeuroMods/Flags/Countries/ad.svg")


if __name__ == "__main__":
    init()
    main()