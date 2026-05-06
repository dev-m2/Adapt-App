import sqlite3
import datetime
import numpy as np 
import pandas as pd
import math
from textwrap import dedent #for removing indentatino from multiline input string
import os #to check what's inside the neuromods folder

def init():
    with sqlite3.connect('flashcards.db') as db:
        cursor = db.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS flashcards (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cue TEXT UNIQUE NOT NULL,
            response TEXT NOT NULL,

            lastReviewRetention INT DEFAULT 20,
            lastReviewDate TEXT DEFAULT (CURRENT_DATE),
            presentRetention INT DEFAULT 20,
            decayRate INT DEFAULT 10,
            import TEXT DEFAULT EMPTY)
        ''')
        db.commit()

def createCard():
    cue = input("What is the cue?: ")
    response = input("What is the response?: ")

    with sqlite3.connect('flashcards.db') as db:
        cursor = db.cursor()
        cursor.execute(f"INSERT INTO flashcards (cue, response) VALUES ('{cue}','{response}')")
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

def updateRetention():
    with sqlite3.connect('flashcards.db') as db:
        cursor = db.cursor()
        df = pd.read_sql_query("SELECT id, lastReviewRetention, lastReviewDate, presentRetention, decayRate FROM flashcards", db)
        
        df["timeSince"] = (pd.Timestamp.now() - pd.to_datetime(df["lastReviewDate"])).dt.days
        df["presentRetention"] = df["lastReviewRetention"] * (math.e ** (-df["decayRate"] * df["timeSince"])) # does calculation
        df["presentRetention"] = df["presentRetention"].clip(0,100)
        df["presentRetention"] = df["presentRetention"].astype(int)
        
        updatedData = list(zip(df["presentRetention"], df["id"]))

        try:
            cursor.executemany("""
                UPDATE flashcards
                SET presentRetention = ?
                WHERE id = ?
            """, updatedData)

            print(f"Rows affected: {cursor.rowcount}")
            db.commit()
            print("✅ Update committed successfully!")

        except Exception as e:
            print("❌ Error: {e}")
            db.rollback()

        print(df.head(),"\n")
        print("New table:")

        viewAll()

def editCard():
    id = input("The card with which ID would you like to edit?: ")
    var = input("Which variable would you like to edit?: ")
    new = input("What should the new value be?: ")

    with sqlite3.connect('flashcards.db') as db:
        cursor = db.cursor()
        cursor.execute(f"UPDATE flashcards SET {var} = '{new}' WHERE id = {id}")
        db.commit()

def review():
    # update lastReview, update presentRetention 

    # within main switch, count how many are below 

    with sqlite3.connect('flashcards.db') as db:
        cursor = db.cursor()
        df = pd.read_sql_query("SELECT id, cue, response, decayRate FROM flashcards WHERE presentRetention < 50", db)

        isReviewing = True
        while isReviewing:
            for row in df.itertuples():

                print(f"Cue: {row.cue}")
                input("Answer: ")
                print(f"Response: {row.response}")

                correctness = input(dedent("""
                    Perfect (2) Okay (1) Bad (0)
                    How well did you do?: """))
                
                match correctness:
                    case "2":
                        newDecayRate = row.decayRate * 0.6
                        presentRetention = 0.95
                    case "1":
                        newDecayRate = row.decayRate * 0.8
                        presentRetention = 0.7
                    case "0":
                        newDecayRate = row.decayRate * 1.4
                        presentRetention = 0.4
                
                cursor.execute(f"""
                    UPDATE flashcards
                    SET decayRate = {newDecayRate},
                        lastReviewDate = (CURRENT_DATE),
                        lastReviewRetention = {presentRetention},
                        presentRetention = {presentRetention}
                    WHERE id = {row.id}""")
                db.commit()

                if input("Review another? (Y/n) ") == "n":
                    isReviewing = False
                    print("Good reviewing!")

def importCards():
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
                    "INSERT OR IGNORE INTO flashcards (cue, response, import) VALUES (?,?,?)",
                    (row['cue'], row['response'], row['import']))
            
            db.commit()

            #df.to_sql('flashcards', db, if_exists='append', index=False)

    else:
        print("That is not a valid neuromod!\n")

def main():
    init()
    isRunning = True
    while isRunning:

        with sqlite3.connect("flashcards.db") as db:
            n = db.execute("SELECT COUNT(*) FROM flashcards WHERE presentRetention < 50").fetchone()[0]

        print("---------------------------")
        print("-Welcome-to-the-Adapt-App!-")
        print("---------------------------")
        print(f"Options: 0 exit; 1 create new card; 2 view all; 3 delete card; 4 update; 5 edit card; 6 review ({n}); 7 import\n")

        choice = input("Choice: ")
        print("")

        match choice:
            case "0":
                print("Goodbye!")
                isRunning = False
            case "1":
                createCard()
            case "2":
                viewAll()
            case "3":
                deleteCard()
            case "4":
                updateRetention()
            case "5":
                editCard()
            case "6":
                review() if n > 0 else print("Nothing to review!\n")
            case "7":
                importCards()
            case _:
                "Invalid input!"



if __name__ == "__main__":
    main()


# NOTE TO SELF:
# (DONE) add review function (with user-done answer checking)
# (doneish) look into SM-2 library (extract numbers?)
# (DONE) look into SQL ? placeholders
# add cosine similary NLP answer checking
# add randomly generated questions -> serialization?
# add second-based timeSince exponential decay
# setup review history table, graphs?
# ! github
# is a property of exponential decay such that I don't need to keep the 'lastReviewRetention' around for a correct calculation...
# ... only the time since 'presentRetention'
# (doneish) csv/text/json importing (look into custom file extensions)
# !? fix weird bug when reviewing multiple cards






#------------------------------------------------------------------
# SM-2 (Old & Simple)

# E-Factor (starts at 2.5, min 1.3)
# Update: EF = EF + (0.1 - (5 - q) * (0.08 + (5 - q) * 0.02))
# Next interval:
# If grade < 3 → reset to 1 day
# Else → interval = previous_interval * EF

# Modern SuperMemo (SM-17 / SM-18+)
# Uses three variables:

# S = Stability (how long you remember something)
# D = Difficulty
# R = Retrievability (probability of recall, decays over time)

# Core formulas (simplified):

# Forgetting curve: R = exp(-t / S)
# (t = time since last review)
# Next interval:
# I = S * multiplier(D, S, R)
# After review, update S and D based on actual recall.

# This is much more advanced than SM-2 because it models memory with continuous values instead of simple multipliers.