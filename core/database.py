import sqlite3
from contextlib import contextmanager
import pandas as pd
import json
from datetime import datetime, timezone

DATABASE_PATH = "adaptations.db"
MAIN_TABLE = "adaptations"

@contextmanager
def connectDB():
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn # Code before yield -> run when entering With
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
                history TEXT DEFAULT '[]'
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS models (
                name TEXT PRIMARY KEY,
                m REAL NOT NULL,
                kp REAL NOT NULL
            )
        """)

        conn.execute("""
            INSERT OR IGNORE INTO models (name, m, kp)
            VALUES ('main_model', 0.35, 0.05)
        """)

        conn.commit()

def get_due_count():
    """Return how many cards are due right now."""
    with connectDB() as conn:
        row = conn.execute(f"""
            SELECT COUNT(*) 
            FROM {MAIN_TABLE}
            WHERE due <= strftime('%Y-%m-%dT%H:%M:%f+00:00', 'now')
        """).fetchone()
        return row[0] if row else 0

def delete_adaptation(adapt_id: str | int | None = None):
    """Delete one card or ALL cards.
    Pass adapt_id = 'ALL' (string) or None to delete everything.
    Returns a message for the user."""
    with connectDB() as conn:
        if str(adapt_id).upper() == "ALL":
            # Optional: ask for confirmation in main.py instead of here
            conn.execute(f"DELETE FROM {MAIN_TABLE}")
            conn.commit()
            return "✅ All adaptations deleted successfully!"

        else:
            # Safe parameterized delete for single card
            result = conn.execute(
                f"DELETE FROM {MAIN_TABLE} WHERE id = ?", 
                (adapt_id,)
            )
            conn.commit()

            if result.rowcount > 0:
                return f"✅ Card #{adapt_id} deleted successfully!"
            else:
                return f"⚠️  No card found with ID {adapt_id}."

def updateDB(content_dict: dict = None, 
             scheduling_dict: dict = None, 
             state_dict: dict = None, 
             adapt_id: int = None,
             due: str = None):
    """Insert or update. New cards automatically get due = now."""
    with connectDB() as conn:
        if adapt_id:  # UPDATE existing card
            updates = []
            params = []

            if content_dict is not None:
                updates.append("content = ?")
                params.append(json.dumps(content_dict))
            if scheduling_dict is not None:
                updates.append("scheduling = ?")
                params.append(json.dumps(scheduling_dict))
            if state_dict is not None:
                updates.append("state = ?")
                params.append(json.dumps(state_dict))
            if due is not None:
                updates.append("due = ?")
                params.append(due)

            if updates:
                sql = f"UPDATE {MAIN_TABLE} SET {', '.join(updates)} WHERE id = ?"
                params.append(adapt_id)
                conn.execute(sql, params)

        else:  # INSERT new card
            content_dict = content_dict or {}
            scheduling_dict = scheduling_dict or {}
            state_dict = state_dict or {}

            # ←←← NEW: give every new card an immediate due date
            if due is None:
                due = datetime.now(timezone.utc).isoformat(timespec='milliseconds')

            conn.execute(f"""
                INSERT INTO {MAIN_TABLE} (content, scheduling, state, due)
                VALUES (?, ?, ?, ?)
            """, (
                json.dumps(content_dict),
                json.dumps(scheduling_dict),
                json.dumps(state_dict),
                due
            ))

        conn.commit()

def toDF(table_name: str = MAIN_TABLE):
    with connectDB() as conn:
        df = pd.read_sql_query(f"SELECT * FROM {table_name}", conn)
        return df

def getModelParams(model_name: str):
    with connectDB() as conn:
        row = conn.execute("""
            select m, kp
            FROM models
            WHERE name = ?
        """, (model_name,)).fetchone()

    if row is None:
        raise ValueError(f"Model '{model_name}' is not found in the database")
    
    return {
        "m": row['m'],
        "kp": row['kp']
    }

def getAdaptData(adapt_id):
    with connectDB() as conn:
        row = conn.execute(
            f"SELECT * FROM {MAIN_TABLE} WHERE id = ?", (adapt_id, )
        ).fetchone()
    
    if row is None:
        return None

    data = dict(row)

    # Convert JSON strings back to Python dicts
    data['content']    = json.loads(data['content']) if data['content'] else {}
    data['scheduling'] = json.loads(data['scheduling']) if data['scheduling'] else {}
    data['state']      = json.loads(data['state']) if data.get('state') else {}
        
    return data