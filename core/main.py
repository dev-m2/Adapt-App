from database import connectDB, initDB, toDF, getModelParams, updateDB, getAdaptData, get_due_count, delete_adaptation
from universal_scheduler import UniversalScheduler
from utils import codeInput, CONTENT_EMPTY, SCHEDULING_DEFAULT, stateDefault
from textwrap import dedent
import json
from datetime import datetime, timezone

def init():
    initDB()
    params = getModelParams("main_model")
    scheduler = UniversalScheduler(params)
    return scheduler

def createAdaptation():
    typeInput = input("What is the adaptation's type? (1 Text; 2 Python Code; 3 Run): ").strip().lower()

    content = CONTENT_EMPTY.copy() # uses utils constant

    match typeInput:
        case "1" | "text" | "":
            content["cue"] = input("What is the cue?: ")
            content["response"] = input("What is the response?: ")
            content["type"] = "text"
        
        case "2" | "py" | "python" | "python code":
            content["code"] = codeInput("Provide the Python code: ")
            content["response"] = "cueEmbedded"
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
            return # stops here
    
    updateDB(
        content_dict = content,
        scheduling_dict = SCHEDULING_DEFAULT, # uses utils constant
        state_dict = stateDefault() # gets current timestamp
    )
    
    print("✅ Adaptation created successfully!")

def review(adapt_id: int, scheduler):
    data = getAdaptData(adapt_id)
    if not data:
        print("Adaptation not found.")
        return

    content = data["content"]
    adapt_type = content.get("type")

    print("\n" + "="*50)

    if adapt_type == "text":
        print(f"Cue: {content.get('cue')}")
        input("Your answer: ")
        print(f"Response: {content.get('response')}")
    elif adapt_type == "run":
        print(content.get("cue"))
        input("Press Enter when you get back...")
        input("What was your time (mm:ss): ")
    else:
        print("Unknown adaptation type.")
        return

    # Ask for rating
    rating_input = input(dedent("""
        Again (1)  Hard (2)  Good (3)  Easy (4)
        How well did you do?: """)).strip().lower()

    if rating_input in ("1", "again"):   grade = 0
    elif rating_input in ("2", "hard"):  grade = 1
    elif rating_input in ("3", "good"):  grade = 2
    elif rating_input in ("4", "easy"):  grade = 3
    else:
        print("Invalid input! Skipping.")
        return

    # FSRS review + fitness/fatigue
    scheduling_dict, state_dict, new_due = scheduler.SchedulerReview(data, grade)

    # Save everything
    updateDB(
        content_dict=None,
        scheduling_dict=scheduling_dict,
        state_dict=state_dict,
        adapt_id=adapt_id,
        due=new_due          # always a proper due date now
    )

    print("✅ Review saved.")

def reviewProcess(scheduler):
    while True:
        df = toDF()
        due_cards = df[df['due'] <= datetime.now(timezone.utc).isoformat()]

        if due_cards.empty:
            print("\nNo cards are due right now!")
            break

        print(f"\nStarting review round — {len(due_cards)} card(s) due.\n")

        for row in due_cards.itertuples():
            review(row.id, scheduler)

        if input("\nReview another round? (Y/n): ").strip().lower() == "n":
            print("Good reviewing!")
            break

def deleteAdaptation():
    choice = input("Delete which card? (Enter ID or type ALL): ").strip()
    
    if choice.upper() == "ALL":
        confirm = input("⚠️  REALLY delete ALL cards? This cannot be undone! (yes/no): ").strip().lower()
        if confirm != "yes":
            print("Delete cancelled.")
            return

    msg = delete_adaptation(choice)   # call the database function
    print(msg)

def viewAdapt():
    print(toDF().to_string())

def main():
    scheduler = init() # initializes DB, returns scheduler

    while True:
        dueCount = get_due_count()

        print("---------------------------")
        print("-Welcome-to-the-Adapt-App!-")
        print("---------------------------")
        print(f"Options: 0 exit; 1 create adapt; 2 view adapt; 3 review ({dueCount}); 4 delete;\n")

        choice = input("Choice: ").strip()

        match choice:
            case "0":
                print("Goodbye!")
                break
            case "1":
                createAdaptation()
            case "2":
                viewAdapt()
            case "3":
                reviewProcess(scheduler)
            case "4":
                deleteAdaptation()
            case _:
                print("Invalid input!")

if __name__ == "__main__":
    main()