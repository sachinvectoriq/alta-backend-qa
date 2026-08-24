
from flask import Flask, request, jsonify
import psycopg2
import os
import datetime
from typing import Any
import json

app = Flask(__name__)

def validate_bearer_token(request, expected_token):
    auth_header = request.headers.get('Authorization', '')
    if not auth_header.startswith('Bearer '):
        return jsonify({"error": "Invalid or missing Authorization header."}), 401
    token = auth_header.split(' ')[1]
    if token != expected_token:
        return jsonify({"error": "Unauthorized. Invalid Bearer token."}), 403
    return None  # No error

DB_CONFIG = {
    'dbname': os.getenv('DB_NAME'),
    'user': os.getenv('DB_USER'),
    'password': os.getenv('DB_PASSWORD'),
    'host': os.getenv('DB_HOST'),
    'port': os.getenv('DB_PORT')
}

def connect_db():
    """Establishes a connection to the PostgreSQL database."""
    try:
        connection = psycopg2.connect(**DB_CONFIG)
        print("Connected to database")
        return connection
    except psycopg2.Error as e:
        print(f"Error connecting to the database: {e}")
        return None

def log_message(connection, level: str, message: str, log_data: dict[str, Any] | None = None, session_id: str | None = None) -> None:
    """
    Logs a message to the database.

    Args:
        connection: The PostgreSQL database connection.
        level: The log level (e.g., 'INFO', 'ERROR').
        message: The log message.
        log_data: A dictionary containing additional data to be logged (optional).
    """
    if connection is None:
        print("Database connection is None. Cannot log message.")
        return  # IMPORTANT: Exit if no connection

    cursor = connection.cursor()
    timestamp = datetime.datetime.now()
    try:
        # Use a parameterized query to prevent SQL injection
        if session_id:  # check if session_id exists
            cursor.execute(
                "INSERT INTO logs (timestamp, level, log, data, session_id) VALUES (%s, %s, %s, %s, %s)",
                # Added session_id
                (timestamp, level, message, json.dumps(log_data) if log_data else None, session_id)
            )
        else:
            cursor.execute(
                "INSERT INTO logs (timestamp, level, log, data, session_id) VALUES (%s, %s, %s, %s, %s)",
                # Added session_id
                (timestamp, level, message, json.dumps(log_data) if log_data else None, None)
            )
        connection.commit()
    except psycopg2.Error as e:
        print(f"Error logging to database: {e}")
        connection.rollback()  # Rollback on error, to avoid partial writes.
    finally:
        cursor.close()


def get_db_connection():
    return psycopg2.connect(
        dbname=DB_CONFIG['dbname'],
        user=DB_CONFIG['user'],
        password=DB_CONFIG['password'],
        host=DB_CONFIG['host'],
        port=DB_CONFIG['port']
    )

@app.route('/core_prompt/get', methods=['GET'])
def get_prompt():
    conn2=connect_db()
    log_message(conn2,"info","fetch core prompt API accessed")
    auth_error = validate_bearer_token(request, 'A7x!G2p@Q9#L')
    if auth_error:
        log_message(conn2,"Error","error with auth section",{"error":auth_error})
        return auth_error

    try:
        conn = get_db_connection()
        cur = conn.cursor()

        # First query: Get max core_prompt_id
        cur.execute("SELECT MAX(core_prompt_id) FROM contextsense_core_prompt")
        max_core_prompt_id_result = cur.fetchone()
        max_core_prompt_id = max_core_prompt_id_result[0]
        log_message(conn2, "info", "Fetched max core_prompt_id", {"max_core_prompt_id": max_core_prompt_id})



        if max_core_prompt_id is None:
            cur.close()
            conn.close()
            return jsonify({"message": "No records found"}), 404

        # Second query: Get the prompt with that ID
        cur.execute("""
            SELECT core_prompt_id, prompt, created_by, created_at
            FROM contextsense_core_prompt
            WHERE core_prompt_id = %s
        """, (max_core_prompt_id,))
        result = cur.fetchone()
        log_message(conn2,"info","DB responded",{"result":str(result)})

        cur.close()
        conn.close()

        if result:
            log_message(conn2,"info","fetch core prompt API responded",{"data":str(result)})
            return jsonify({
                "core_prompt_id": result[0],  # Always returns latest core_prompt_id
                "prompt": result[1],
                "created_by": result[2],
                "created_at": result[3].strftime('%a, %d %b %Y %H:%M:%S GMT')
            }), 200
        else:
            log_message(conn2,"error","No record found in db error code:404")
            return jsonify({"message": "No records found"}), 404

    except Exception as e:
        log_message(conn2,"error","fetch core prompt Api failed",{"error":str(e)})
        return jsonify({"error": str(e)}), 500
