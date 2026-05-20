import sqlite3
from datetime import datetime, timezone, timedelta
import numpy as np 
import pandas as pd
import math
import random
from textwrap import dedent #for removing indentation from multiline input string
import os #to check what's inside the neuromods folder
from sentence_transformers import SentenceTransformer, util
from fsrs import Scheduler, Card, Rating, ReviewLog
import json
import csv # for exporting flashcards
import time
import torch
import subprocess # for chaffa image rendering
import shutil # for chaffa image rendering, PATH finding???
import statistics

def init():
    # Database setup
    with sqlite3.connect('flashcards.db') as db:
        cursor = db.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS flashcards (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cue JSON UNIQUE NOT NULL,
            response TEXT NOT NULL,
            type TEXT NOT NULL DEFAULT "text",
            state INT DEFAULT 1,
            step INT DEFAULT 0,
            stability REAL DEFAULT NULL,
            difficulty REAL DEFAULT NULL,
            due TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%f+00:00', 'now')),
            lastReview TEXT DEFAULT NULL,
            r REAL NOT NULL DEFAULT 1.0,
            source TEXT DEFAULT custom,
            supercompEndDate TEXT DEFAULT NULL,
            supercompRating TEXT DEFAULT NULL,
            supercompPerformance TEXT DEFAULT NULL,
            history TEXT DEFAULT '[]')
        ''')
        db.commit()
    

def codeInput(openingText = ""):
    if openingText: print(openingText) # checks if it's not empty
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

def createAdaptation():
    adaptType = input("What is the adaptation's type? (1 Text; 2 Python Code): ")

    match adaptType.lower():
        case "1" | "text" | "":
            cue = input("What is the cue?: ")
            response = input("What is the response?: ")
            adaptType = "text"

        case "2" | "py" | "python" | "python code":
            isEmbedded = input("Will the response be made within the cue code? (Y/n): ")

            if isEmbedded.lower() == "y" or "" or "yes":
                cue = codeInput("Provide the cue function using Python (that returns Cue, Response): ")
                response = "embeddedWithinCue"
                adaptType = "pythonResponseEmbedded"

            elif isEmbedded.lower() == "n":
                cue = codeInput("Provide the cue function using Python (that returns Cue): ")
                response = codeInput("Provide the response function using Python (that returns Response): ")
                adaptType = "python"
            else:
                print("Faulty input!")

    #tempDict = {"cue":cue, "response":response, "type":adaptType}
    #tempJSON = json.dumps(tempDict, ensure_ascii=False, indent=None) # allows non-english chars; no \n indentation;

    with sqlite3.connect('flashcards.db') as db:
        cursor = db.cursor()
        db.execute("INSERT INTO flashcards (cue, response, type) VALUES (?, ?, ?)", (cue, response, adaptType))
        db.commit()

    print("✅ Card created successfully!")


def viewAll():
    print("-----------------------------------Flashcard Table----------------------------------")
    with sqlite3.connect('flashcards.db') as db:
        dfFull = pd.read_sql_query("SELECT * FROM flashcards", db)
        dfFull = dfFull.set_index("id")
        print(dfFull.to_string())
    print("------------------------------------------------------------------------------------")

def deleteCard():
    id = input("The card with which ID would you like to delete? (ALL to delete all): ")

    with sqlite3.connect('flashcards.db') as db:
        cursor = db.cursor()
        if id == "ALL":
            cursor.execute(f"DELETE FROM flashcards")
            print("All cards deleated successfully!")
        else:
            cursor.execute(f"DELETE FROM flashcards WHERE id = {id}")
            print("Card deleated successfully!")
        db.commit()

def editCard():
    id = input("The card with which ID would you like to edit?: ")
    var = input("Which variable would you like to edit?: ")
    new = input("What should the new value be?: ")

    with sqlite3.connect('flashcards.db') as db:
        cursor = db.cursor()
        cursor.execute(f"UPDATE flashcards SET {var} = '{new}' WHERE id = {id}")
        db.commit()

def review():
    with sqlite3.connect('flashcards.db') as db:
        cursor = db.cursor()
        df = pd.read_sql_query("SELECT * FROM flashcards WHERE due <= strftime('%Y-%m-%dT%H:%M:%f+00:00', 'now') AND state !=5", db)

    isReviewing = True
    while isReviewing:
        for row in df.itertuples():
            if row.type == "text":
                print(f"Cue: {row.cue}")
                answer = input("Answer: ")
                print(f"Response: {row.response} (similarity: {nlpCheck(answer, row.response)})")

            elif row.type == "pythonResponseEmbedded":
                cueDict = json.loads(row.cue)
                cueContent = cueDict.get("content")

                namespace = {}
                exec(cueContent, globals(), namespace)
                print(f"Cue: {namespace['cue']}")
                answer = input("Answer: ")
                print(f"Response: {namespace['response']} (similarity: {nlpCheck(answer, namespace['response'])})")

            elif row.type == "image-text":
                cueDict = json.loads(row.cue)
                cueImagePath = cueDict.get("path")
                cueContent = cueDict.get("content")

                response = row.response

                renderImage(cueImagePath)
                print(cueContent)
                answer = input("Answer: ")
                print(f"Response: {row.response} (similarity: {nlpCheck(answer, row.response)})")

            elif row.type == "imageAuto":
                cueDict = json.loads(row.cue)
                cueImagePath = cueDict.get("path")
                cueContent = cueDict.get("content")

                renderImage(cueImagePath)

                namespace = {}
                exec(cueContent, globals(), namespace)
                print(f"Cue: {namespace['cue']}")
                answer = input("Answer: ")
                print(f"Response: {namespace['response']} (similarity: {nlpCheck(answer, namespace['response'])})")

            elif row.type == "run":
                cueDict = json.loads(row.cue)
                cueContent = cueDict.get("content")

                print(cueContent)
                input("Press anything  when you get back.")
                answer = input("What was your time (mm:ss): ")

                delayedRunReview(row.id, answer)
                
                print("Happy reviewing!")
                isReviewing = False
                break


            rating = input(dedent("""
                     Again (1) Hard (2) Good (3) Easy (4)
                     How well did you do?: """))
            
            tempDict = {
                "card_id": row.id,
                "state": row.state,
                "step": row.step,
                "stability": row.stability,
                "difficulty": row.difficulty,
                "due": row.due,
                "last_review": row.lastReview
            }

            tempCard = Card.from_json(json.dumps(tempDict))

            preReviewR = scheduler.get_card_retrievability(tempCard)

            match rating.lower():
                case "again" | "1":
                    tempCard, review_log = scheduler.review_card(tempCard, Rating.Again)
                case "hard" | "2":
                    tempCard, review_log = scheduler.review_card(tempCard, Rating.Hard)

                case "good" | "3":
                    tempCard, review_log = scheduler.review_card(tempCard, Rating.Good)
                
                case "easy" | "4":
                    tempCard, review_log = scheduler.review_card(tempCard, Rating.Easy)
                case _:
                    print("Faulty input!")
            
            saveHistory(row.id, review_log, tempCard, preReviewR)

            tempDict = json.loads(tempCard.to_json()) # and back to Python dictionary

            with sqlite3.connect('flashcards.db') as db:
                db.execute("""
                    UPDATE flashcards
                    SET state = ?, step = ?, stability = ?, difficulty = ?, due = ?, lastReview = ?
                    WHERE id = ?
                """, (
                    tempDict.get('state'),
                    tempDict.get('step'),
                    tempDict.get('stability'),
                    tempDict.get('difficulty'),
                    tempDict.get('due'),
                    tempDict.get('last_review'),
                    row.id
                ))
                db.commit()
            
            if input("Review another? (Y/n) ") == "n":
                print("Good reviewing!")
                isReviewing = False
                break

def supercompReview(id, rating, performance):
    pass
    # every main() checks for state = 5 AND (supercompDate has passed) <---- OR JUST THIS
    # for every: calls supercompReview(id, rating, performance)
    # builds tempCard by SELECT using ID; reviews it using rating, and adds addHistory(review_log, performance)
    # clears supercomp columns


def delayedRunReview(id, performance):
    with sqlite3.connect('flashcards.db') as db:
        history = db.execute("""
            SELECT history 
            FROM flashcards 
            WHERE id = ?
        """, (id,)).fetchone()

        performanceSeconds = timeToSeconds(performance)

        # If history is a JSON string from the database
        if isinstance(history, str):
            history = json.loads(history)

        # Now safely extract the times
        times = [entry['time'] for entry in history 
                if isinstance(entry, dict) and 'time' in entry]

        if times:
            mean = statistics.mean(times)
            stdDev = statistics.std(times) if len(times) > 0 else 0
        
            # Suggested rating logic
            zScore = (performanceSeconds - mean) /stdDev
            if zScore < -1.0:
                suggestedRating = "Easy"
            elif zScore < 0.0:
                suggestedRating = "Good"
            elif zScore < 1.0:
                suggestedRating = "Hard"
            else:
                suggestedRating = "Again"

            print(f"Your suggested rating is: \"{suggestedRating}\"")

        else:
            print("This is your first time reviewing this!")


        rating = input(dedent("""
                     Again (1) Hard (2) Good (3) Easy (4)
                     How would you like to review this run?: """))

        match rating.lower():
                case "again" | "1":
                    supercompReview = "1"
                case "hard" | "2":
                    supercompReview = "2"
                case "good" | "3":
                    supercompReview = "3"
                case "easy" | "4":
                    supercompReview = "4"
                case _:
                    print("Faulty input!")
        
        supercompIntervalConstant = 2
        supercompEndDate = (datetime.utcnow() + timedelta(days=supercompIntervalConstant)).strftime('%Y-%m-%dT%H:%M:%f+00:00')

        db.execute("""
            UPDATE flashcards
            SET state = ?,
                supercompEndDate = ?,
                supercompRating = ?,
                supercompPerformance = ?
            WHERE id = ?
            """, (5, supercompEndDate, supercompReview, performanceSeconds, id))

        db.commit()

        print("Supercomposition successfully set!")



def timeToSeconds(timeString):
    # AI made function
    parts = timeString.strip().split(':') 
    
    if len(parts) == 2:        # mm:ss
        minutes, seconds = map(int, parts)
        return minutes * 60 + seconds
    elif len(parts) == 3:      # h:mm:ss
        hours, minutes, seconds = map(int, parts)
        return hours * 3600 + minutes * 60 + seconds
    else:
        raise ValueError(f"Invalid time format: {time_str}")

    # get tempJSON
    # get id, select row, get history, calculate std mean, 


# AI made function; render images using chafa
def renderImage(path: str, width: int = 80, height: int = 40):

    if not os.path.exists(path):
        print(f"❌ Image not found: {path}")
        return False
    try:
        subprocess.run([
            "chafa",
            "--size", f"{width}x{height}",
            "--colors", "full",           # or "256" / "16"
            "--symbols", "all",
            path
        ], check=True)
        return True
    except FileNotFoundError:
        print("❌ 'chafa' command not found. Install it with: sudo apt install chafa")
        return False
    except Exception as e:
        print(f"Error displaying image: {e}")
        return False



# def render_image2(path: str):
#     try:
#         # This finds chafa using the same method as your terminal
#         chafa_path = shutil.which("chafa")
#         if not chafa_path:
#             print("❌ chafa not found in PATH")
#             return
        
#         subprocess.run([chafa_path, "--size", "80x40", path], check=True)
        
#     except FileNotFoundError:
#         print("❌ chafa is still not found")
#     except Exception as e:
#         print(f"Error: {e}")

# def render_image3(path: str):
#     try:
#         subprocess.run(f"chafa --size 80x40 '{path}'", shell=True, check=True)
#     except Exception as e:
#         print(f"Error rendering image: {e}")

def importAdapt():
    # look in folder, find files, turn csv -> df? -> append rows in sql table
    # mark rows as imported, so that you can delete them later
    # check if the cards already exist so that you don't double import

    itemList = os.listdir("neuromods")
    for i in itemList:
        print(i)
    print("")

    choice = input("Which one would you like to import?: ")

    if os.path.isfile(f"neuromods/{choice}"):
        df = pd.read_csv(f"neuromods/{choice}")

        with sqlite3.connect('flashcards.db') as db:
            cursor = db.cursor()

            for _, row in df.iterrows():
                cursor.execute(
                    "INSERT OR IGNORE INTO flashcards (cue, response, type, source) VALUES (?,?,?,?)",
                    (row['cue'], row['response'], row['type'], row['source']))
            
            db.commit()

            #df.to_sql('flashcards', db, if_exists='append', index=False)

    else:
        print("That is not a valid neuromod!\n")

def nlpCheck(text1, text2):
    
    #text1 = "The quick brown fox jumps over the lazy dog."
    #text2 = "A fast brown canine leaps above a sleepy puppy."

    #text1 = input("Text 1: ")
    #text2 = input("Text 2: ")

    emb1 = model.encode(text1, normalize_embeddings=True)
    emb2 = model.encode(text2, normalize_embeddings=True)

    similarity = util.cos_sim(emb1, emb2).item()   # → ~0.78–0.92 depending on model
    return str(round(similarity * 100))+"%"


def test():
    pass


def updateR():
    with sqlite3.connect('flashcards.db') as db:

        df = pd.read_sql_query("""
            SELECT id, state, step, stability, difficulty, due, lastReview
            FROM flashcards""", db)

        # Normalize timestamps?
        df["lastReview"] = pd.to_datetime(df["lastReview"], errors="coerce", utc=True) # Troubleshooting fixing timezone stuff
        df["due"] = pd.to_datetime(df["due"], errors="coerce", utc=True)

        scheduler = Scheduler() # for FSRS
        now = datetime.now(timezone.utc) 

        for row in df.itertuples():
            tempDict = {
                "card_id": row.id,
                "state": row.state,
                "step": row.step,
                "stability": row.stability,
                "difficulty": row.difficulty,
                "due": row.due.isoformat(), # ensures ISO 8601?
                "last_review": row.lastReview.isoformat() # ensures ISO 8601?
            }

            tempCard = Card.from_json(json.dumps(tempDict))

            R = scheduler.get_card_retrievability(
                tempCard,
                current_datetime=now)
            
            db.execute(
                "UPDATE flashcards SET r = ? WHERE id = ?",
                (R, row.id)
            )
        
        db.commit()

def export():
    os.makedirs('neuromods', exist_ok=True)

    with sqlite3.connect('flashcards.db') as db:
        cursor = db.cursor()
        cursor.execute("SELECT * FROM flashcards")
        rows = cursor.fetchall()
        columns = [desc[0] for desc in cursor.description]

        with open('neuromods/flashcards_export.csv', 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(columns)
            writer.writerows(rows)

def saveHistory(card_id, review_log, tempCard, pre_review_r):
    reviewDict = {
        "time": review_log.review_datetime.isoformat(),
        "rating": int(review_log.rating),
        "stability": round(tempCard.stability, 4),
        "difficulty": round(tempCard.difficulty, 4),
        "pre-review r": round(pre_review_r, 4),
        "post-review r": round(scheduler.get_card_retrievability(tempCard), 4)
    }

    print("reviewDICT:")
    print(reviewDict)

    with sqlite3.connect('flashcards.db') as db:
        row = db.execute("SELECT history FROM flashcards WHERE id = ?", 
                        (card_id,)).fetchone()
        
        history = json.loads(row[0]) if row and row[0] else []
        history.append(reviewDict)
        
        db.execute("UPDATE flashcards SET history = ? WHERE id = ?", 
                   (json.dumps(history, ensure_ascii=False), card_id))
        db.commit()

    with sqlite3.connect('flashcards.db') as db:
        cursor = db.cursor()
        

    # isReviewing = True
    # while isReviewing:
    #     for row in df.itertuples():



def main():
    isRunning = True
    while isRunning:
        with sqlite3.connect("flashcards.db") as db:
            n = db.execute("SELECT COUNT(*) FROM flashcards WHERE due <= strftime('%Y-%m-%dT%H:%M:%f+00:00', 'now') AND state != 5").fetchone()[0]

            # df = pd.read_sql_query("SELECT id FROM flashcards WHERE supercompEndDate <= strftime('%Y-%m-%dT%H:%M:%f+00:00', 'now') AND state !=5", db)

        print("---------------------------")
        print("-Welcome-to-the-Adapt-App!-")
        print("---------------------------")
        print(f"Options: 0 exit; 1 create; 2 view all; 3 delete; 4 update R; 5 edit; 6 review ({n}); 7 import; 8 sim test; 9 export\n")

        choice = input("Choice: ")
        print("")

        match choice:
            case "0":
                print("Goodbye!")
                isRunning = False
            case "1":
                createAdaptation()
            case "2":
                viewAll()
            case "3":
                deleteCard()
            case "4":
                updateR()
            case "5":
                editCard()
            case "6":
                review() if n > 0 else print("Nothing to review!\n")
            case "7":
                importAdapt()
            case "8":
                nlpCheck()
            case "9":
                export()
            case "999":
                test()
            case "998":
                testCreateSet()
            case _:
                "Invalid input!"

def testCreateSet():
    content = dedent("""a = random.randint(1,9)
    b = random.randint(1,9)
    cue = f"{a} + {b}?"
    response = str(a + b)""")

    cue_json = json.dumps({"content": content})   # Proper JSON

    data = [{
        "cue": cue_json,
        "response": "embeddedWithinCue",
        "type": "pythonResponseEmbedded",
        "source": "mathAutoTest"
    }]

    df = pd.DataFrame(data)
    df.to_csv('neuromods/test_math.csv', index=False, encoding='utf-8')

    print("CSV created correctly.")
    print("Cue column value:\n", cue_json)


    # data = [
    #     {
    #         "cue": json.dumps({
    #             "content": "What is flag?",
    #             "path": "neuromods/flags/images/sweden.png"
    #         }),
    #         "response": "Sweden",
    #         "type": "image-text",
    #         "source": "flags.nm"
    #     },
    #     {
    #         "cue": json.dumps({
    #             "content": "What is this flag?",
    #             "path": "neuromods/flags/images/united kingdom.png"
    #         }),
    #         "response": "United Kingdom",
    #         "type": "image-text",
    #         "source": "flags.nm"
    #     },
    # ]

    # df = pd.DataFrame(data)
    # df.to_csv('neuromods/flags2.csv', index=False, encoding='utf-8')

    # print("CSV created successfully!")



if __name__ == "__main__":
    
    # print("Python PATH:")
    # print(os.environ.get('PATH'))

    # print("\nshutil.which('chafa') →", shutil.which("chafa"))

    scheduler = Scheduler() # for FSRS
    model = SentenceTransformer("all-MiniLM-L6-v2") # running on GPU causes problems (30+ secs) but better accuracy (0.99 on test)
    # now running it without specifying cpu makes it run fine, but with worse accuracy; perhaps it was an error (0.99 on test)
    
    #print(torch.cuda.is_available())
    #print(torch.cuda.current_device() if torch.cuda.is_available() else "CPU")

    #print(model)

    init()
    main()
