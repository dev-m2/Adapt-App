from .utils import CONTENT_EMPTY, SCHEDULING_DEFAULT, STATE_DEFAULT # for updateDB()
import sqlite3
from contextlib import contextmanager # for connectDB()
import json         # for updateDB()
import pandas as pd # for dbDataFrame()



DATABASE_PATH = "../adaptations.db"
MAIN_TABLE = "adaptations"

@contextmanager
def connectDB():
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row # returned as Row objects (index/name accessible), not tuples
    try:
        yield conn   # Code before yield -> run when entering With
    finally:
        conn.close() # Code after yield -> run when exiting With

def initDB():
    with connectDB() as conn:
        conn.execute(f"""
            CREATE TABLE IF NOT EXISTS {MAIN_TABLE} (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                content TEXT,
                scheduling TEXT,
                state TEXT,
                due TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%f+00:00', 'now')),
                source TEXT DEFAULT custom,
                history TEXT DEFAULT '[]')
            """)

        conn.commit()


def updateDB(
        adapt_id: int = None,
        content_dict: dict = None, 
        scheduling_dict: dict = None, 
        state_dict: dict = None,
        newDue = None,
        source: str = None):
    
    with connectDB() as conn:
        # Insert
        if adapt_id is None:
            conn.execute(
                f"""
                INSERT INTO {MAIN_TABLE} (content, scheduling, state, source)
                VALUES (?, ?, ?, ?)
                """,
            (
                json.dumps(content_dict    or CONTENT_EMPTY),      # utils constant
                json.dumps(scheduling_dict or SCHEDULING_DEFAULT), # utils constant
                json.dumps(state_dict      or STATE_DEFAULT()),    # utils constant func
                source or "import" # if not specified
            ))

        # Update
        else:
            row = conn.execute(
                f"SELECT content, scheduling, state, due FROM {MAIN_TABLE} WHERE id = ?",
                (adapt_id,)).fetchone()

            if not row:
                raise ValueError(f"No record found for id {adapt_id}")

            content, scheduling, state, due = row["content"], row["scheduling"], row["state"], row["due"] # old stuff

            # Checks if new stuff is present -> overwrites
            if content_dict is not None:
                content = content_dict
            if scheduling_dict is not None:
                scheduling = json.dumps(scheduling_dict)
            if state_dict is not None:
                state = state_dict
            if newDue is not None:
                due = newDue
            
            conn.execute(
                f"""
                UPDATE {MAIN_TABLE} SET content = ?, scheduling = ?, state = ?, due = ?
                WHERE id = ?
                """,
                (
                    content, scheduling, state, due, adapt_id
                )
            )

        conn.commit()


def dbDataFrame(table_name: str = MAIN_TABLE):
    with connectDB() as conn:
        df = pd.read_sql_query(f"SELECT * FROM {table_name}", conn)
    
    df["id"] = df["id"].astype(str)
    df = df.set_index("id")

    return df


def deleteAdaptation(
        adapt_id: str | int | None = None,
        table_name: str = MAIN_TABLE):
    
    with connectDB() as conn:
        if str(adapt_id.strip()) == "ALL":
            conn.execute(f"DELETE FROM {table_name}")
            conn.commit()
            print("✅ All adaptations deleted successfully!")
        
        else:
            cursor = conn.execute(f"DELETE FROM {table_name} WHERE id = ?", (adapt_id,))
            conn.commit()
        
            if cursor.rowcount > 0:
                print(f"✅ Card #{adapt_id} deleted successfully!\n")
            else:
                print(f"⚠️ No card found with ID {adapt_id}.\n")


def getAdaptData(adapt_id: str):
    with connectDB() as conn:
        row = conn.execute(f"SELECT * FROM {MAIN_TABLE} WHERE id = ?", (adapt_id, )).fetchone()
    
    if row is None: # id validity check
        return None

    data = dict(row)

    # Convert JSON strings back to Python dicts
    data['content']    = json.loads(data['content']) if data['content'] else {}
    data['scheduling'] = json.loads(data['scheduling']) if data['scheduling'] else {}
    data['state']      = json.loads(data['state']) if data.get('state') else {}
        
    # returns full data, content, and type; for _review()
    return data, data['content'], data['content'].get('type') 


def dueCount():
    with connectDB() as conn:
        row = conn.execute(f"""
            SELECT COUNT(*) 
            FROM {MAIN_TABLE}
            WHERE due <= strftime('%Y-%m-%dT%H:%M:%f+00:00', 'now')
        """).fetchone()
        return row[0] if row else 0