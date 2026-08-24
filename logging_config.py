import os
import psycopg2
from datetime import datetime, timezone
import threading
from typing import List, Tuple, Optional, Union, Any
import json
import logging
from dotenv import load_dotenv
from psycopg2.extras import Json
import sys

load_dotenv()

logging.basicConfig(
    level=logging.INFO,  # or DEBUG for more verbosity
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(sys.stderr)
    ]
)

# --- PostgreSQL DB Configuration ---
DB_CONFIG = {
    'dbname': os.getenv('DB_NAME'),
    'user': os.getenv('DB_USER'),
    'password': os.getenv('DB_PASSWORD'),
    'host': os.getenv('DB_HOST'),
    'port': os.getenv('DB_PORT')
}

# --- Thread-safe In-Memory Logging Buffer ---
LOG_BUFFER: List[Tuple] = []
LOG_LOCK = threading.Lock()
MAX_BUFFER_SIZE = 1000  # Optional auto-flush threshold

# --- Logging Schema: (timestamp, level, message, user_id, data_json) ---

def connect_db():
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        logging.info("Connected to database.")
        return conn
    except Exception as e:
        logging.error(f"Database connection failed: {e}")
        return None

def log(level: str, message: str, data: Any = None, user_name: Optional[str] = None):
    timestamp = datetime.now(timezone.utc)
    # Convert data to Json object only if it's not None and is a dict/list
    if data is not None and isinstance(data, (dict, list)):
        data = Json(data)

    log_entry = (timestamp, level, message, data, user_name)
    with LOG_LOCK:
        LOG_BUFFER.append(log_entry)

def flush() -> Tuple[bool, str]: # Return type hint updated to indicate (success_status, message)
    with LOG_LOCK:
        if not LOG_BUFFER:
            message = "No logs to flush."
            logging.info(message)
            return True, message # Return success status and message

        buffer_copy = LOG_BUFFER[:]
        LOG_BUFFER.clear()

    conn = connect_db()
    if not conn:
        with LOG_LOCK:
            LOG_BUFFER.extend(buffer_copy) # Restore buffer if connection fails
        message = "Flush failed: DB connection error. Restoring buffer."
        logging.warning(message)
        return False, message # Return failure status and detailed message

    try:
        with conn.cursor() as cursor:
            insert_query = "INSERT INTO alta_logs (timestamp, level, message, data, user_name) VALUES (%s, %s, %s, %s, %s)"
            cursor.executemany(insert_query, buffer_copy)
            conn.commit()
            message = "Flush successful."
            logging.info(message)
            return True, message # Return success status and message

    except Exception as e:
        message = f"Flush failed with DB error: {e}"
        logging.exception("Flush failed with DB error:") # Logs the full traceback for debugging
        logging.error(f"Error details: {e}") # Logs the specific error message
        with LOG_LOCK:
            LOG_BUFFER.extend(buffer_copy) # Restore buffer if insertion fails
        return False, message # Return failure status and error message
    finally:
        if conn: # Ensure conn exists before trying to close
            conn.close()
            buffer_copy.clear()
            logging.debug("Database connection closed after flush.")
