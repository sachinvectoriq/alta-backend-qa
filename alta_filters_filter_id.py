from flask import Flask, request, jsonify
import psycopg2
from psycopg2 import sql
import datetime
import os
from typing import Any
import json

app = Flask(__name__)


def validate_bearer_token(request, expected_token):
    """
    Validates the Bearer token from the Authorization header in the request.
    Returns an error response if invalid; otherwise, returns None.
    """
    auth_header = request.headers.get('Authorization', '')
    if not auth_header.startswith('Bearer '):
        return jsonify({"error": "Invalid or missing Authorization header."}), 401
    token = auth_header.split(' ')[1]
    if token != expected_token:
        return jsonify({"error": "Unauthorized. Invalid Bearer token."}), 403
    return None  # No error


# Database connection parameters
DB_CONFIG = {
    'dbname': os.getenv('DB_NAME'),  # 'settings_db' is the default if env variable is not set
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


def get_alta_filter_by_id(filter_id):
    connection = None
    try:
        # Connect to the PostgreSQL database
        connection = psycopg2.connect(
            dbname=DB_CONFIG['dbname'],
            user=DB_CONFIG['user'],
            password=DB_CONFIG['password'],
            host=DB_CONFIG['host'],
            port=DB_CONFIG['port']
        )
        cursor = connection.cursor()

        # Define the SQL query
        query = sql.SQL("SELECT * FROM alta_filters WHERE id = %s")

        # Execute the query
        cursor.execute(query, (filter_id,))

        # Get column names
        column_names = [desc[0] for desc in cursor.description]

        # Fetch the result
        result = cursor.fetchone()

        # If no record found
        if result is None:
            return None, "No record found with the specified ID"

        # Convert the result to a dictionary with datetime handling
        result_dict = {}
        for i, col in enumerate(result):
            # Convert datetime objects to strings
            if isinstance(col, datetime.datetime):
                result_dict[column_names[i]] = col.isoformat()
            else:
                result_dict[column_names[i]] = col

        return result_dict, None

    except Exception as error:
        return None, str(error)

    finally:
        # Close the database connection
        if connection:
            cursor.close()
            connection.close()


@app.route('/alta_filters/id', methods=['GET'])
def get_filter():
    conn=connect_db()
    log_message(conn,"info","alta_filters/id accessed")
    auth_error = validate_bearer_token(request, 'A7x!G2p@Q9#L')  # Replace 'A7x!G2p@Q9#L' with your actual token
    if auth_error:
        return auth_error

    # Get filter ID from query parameter
    filter_id = request.args.get('id')

    # Validate input parameter
    if not filter_id:
        log_message(conn,"Error",f"(Missing required query parameter: {id}), 400)")
        return jsonify({
            "status": "error",
            "message": "Missing required query parameter: id"
        }), 400

    # Validate that ID is an integer
    try:
        filter_id = int(filter_id)
    except ValueError:
        log_message(conn, "Error", f"(ID must be an integer), 400)")
        return jsonify({
            "status": "error",
            "message": "ID must be an integer"
        }), 400

    # Call the query function
    result, error = get_alta_filter_by_id(filter_id)

    if error and "No record found" in error:
        log_message(conn,"error",f"no record associated with the id provided {id}")
        return jsonify({
            "status": "error",
            "message": error
        }), 404
    elif error:
        log_message(conn,"error","error with database",{"error":error,"code":500})
        return jsonify({
            "status": "error",
            "message": f"Database error: {error}"
        }), 500

    # Return result
    log_message(conn,"info","Api responded with success message",{"data":result})
    return jsonify({
        "status": "success",
        "data": result
    }), 200


if __name__ == "__main__":
    # Use environment variable for port if available, otherwise default to 5000
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
