import psycopg2
import os
from flask import Flask, request, jsonify
from logging_config import log, flush  # Uncommented: Import log and flush functions
import datetime  # Import datetime (though not used for dates in this API, keeping for consistency)

app = Flask(__name__)

DB_CONFIG = {
    'dbname': os.getenv('DB_NAME'),
    'user': os.getenv('DB_USER'),
    'password': os.getenv('DB_PASSWORD'),
    'host': os.getenv('DB_HOST'),
    'port': os.getenv('DB_PORT')
}

# Define a list of allowed table names for security
ALLOWED_TABLES = [
    'user_text_trans_log',
    'user_docu_trans_log',
    'contextsense'  # contextsense is now included
]

# List of users to exclude from the results for relevant tables
EXCLUDED_USERS = [
    'Vinayak Inamadar', 'Chanbasava Koti', 'Sherlock5', 'Sachin Bhusanurmath',
    'Dinesh Rout', 'Santosh Sohani', 'Bharatkumar Salalli', 'Vinayak Inamadhar',
    'Harsh Aneppanavar', 'test', 'test1', 'test2', 'test3', 'test4', 'test5', 'Test User', 'test6', 'test7',
    'postman_test_user'
]

# Mapping of table names to their user column names for exclusion logic
# Note: For 'contextsense', the user column is in the JOINed 'user_text_trans_log' table (T2.user)
TABLE_USER_COLUMNS = {
    'user_text_trans_log': 'user',
    'user_docu_trans_log': 'user',
    'contextsense': 'T2.user'  # Explicitly note the alias for contextsense join
}


def validate_bearer_token(request, expected_token, user_name: str = None):
    """
    Validates the Bearer token from the Authorization header in the request.
    Returns an error response (jsonify, status_code) if invalid; otherwise, returns None.
    """
    auth_header = request.headers.get('Authorization', '')
    log("INFO", "Attempting to validate Bearer token.", data={"auth_header_present": bool(auth_header)}, user_name=user_name)

    parts = auth_header.split(' ')
    if not auth_header.startswith('Bearer ') or len(parts) != 2:
        log("WARNING", "Invalid or missing Authorization header format.", data={"auth_header": auth_header}, user_name=user_name)
        flush()
        return jsonify({"error": "Invalid or missing Authorization header."}), 401

    token = parts[1]

    if token != expected_token:
        log("ERROR", "Unauthorized access attempt: Invalid Bearer token.", data={"provided_token_prefix": token[:5] + "..."}, user_name=user_name)
        flush()
        return jsonify({"error": "Unauthorized. Invalid Bearer token."}), 403

    log("INFO", "Bearer token validated successfully.", user_name=user_name)
    flush()
    return None


@app.route('/table_row_count', methods=['GET'])
def get_table_row_count():
    """
    Fetches the number of rows in a specified database table.
    Applies user exclusion for relevant tables.
    Requires 'table_name' as a query parameter.
    Returns the count of rows.
    Requires Bearer token authentication.
    """
    user_name = request.args.get('user_name', None)  # Default to anonymous if not provided
    table_name = request.args.get('table_name')

    log("INFO", f"API endpoint to get table row count accessed.", data={"table_name": table_name}, user_name=user_name)

    # 1. Validate Bearer Token
    auth_error = validate_bearer_token(request, 'A7x!G2p@Q9#L', user_name)
    if auth_error:
        return auth_error

    # 2. Validate table_name for security
    if not table_name:
        log("WARNING", "'table_name' query parameter is missing.", user_name=user_name)
        flush()
        return jsonify({"error": "Missing 'table_name' query parameter."}), 400

    if table_name not in ALLOWED_TABLES:
        log("WARNING", f"Attempt to access unauthorized table: {table_name}", data={"allowed_tables": ALLOWED_TABLES}, user_name=user_name)
        flush()
        return jsonify({"error": f"Unauthorized table name. Allowed tables: {', '.join(ALLOWED_TABLES)}."}), 403

    conn = None
    cur = None

    try:
        log("INFO", f"Attempting to connect to database to count rows in table: {table_name}.", user_name=user_name)
        conn = psycopg2.connect(**DB_CONFIG)
        cur = conn.cursor()

        # Initialize base query and parameters
        base_query = ""
        query_params = []

        # Determine the query based on table_name
        if table_name == 'contextsense':
            # Special query for contextsense involving a join
            base_query = """
                SELECT T1.modifier_type, T1.modifier_value, T1.system_prompt, T1.user_prompt, T1.refined_text,
                       T1.explanation, T2.user, T2.source_text, T2.translated_text, T2.source_language,
                       T2.target_language, T2.character_count, T2.vendor, T2.date_and_time
                FROM public.contextsense T1
                INNER JOIN public.user_text_trans_log T2
                ON T1.log_id=T2.log_id
            """
            # Add user exclusion for contextsense (applies to T2.user)
            if EXCLUDED_USERS:
                user_column = TABLE_USER_COLUMNS[table_name]  # This will be 'T2.user'
                placeholders = ', '.join(['%s'] * len(EXCLUDED_USERS))
                base_query += f" WHERE {user_column} NOT IN ({placeholders})"
                query_params.extend(EXCLUDED_USERS)
                log("INFO", f"Applying user exclusion for table '{table_name}' using column '{user_column}'.", data={"excluded_users_count": len(EXCLUDED_USERS)}, user_name=user_name)
            else:
                log("INFO", f"No user exclusion applied for table '{table_name}'.", user_name=user_name)

            # Wrap the base_query in a COUNT(*) query
            count_query = f"SELECT COUNT(*) FROM ({base_query}) AS subquery;"

        else:
            # Standard COUNT(*) query for user_text_trans_log and user_docu_trans_log
            count_query = f"SELECT COUNT(*) FROM public.{table_name}"
            # Add user exclusion for these tables
            if EXCLUDED_USERS:
                user_column = TABLE_USER_COLUMNS[table_name]  # This will be 'user'
                placeholders = ', '.join(['%s'] * len(EXCLUDED_USERS))
                count_query += f" WHERE {user_column} NOT IN ({placeholders})"
                query_params.extend(EXCLUDED_USERS)
                log("INFO", f"Applying user exclusion for table '{table_name}' using column '{user_column}'.", data={"excluded_users_count": len(EXCLUDED_USERS)}, user_name=user_name)
            else:
                log("INFO", f"No user exclusion applied for table '{table_name}'.", user_name=user_name)

        log("INFO", f"Executing query for row count.", data={"query": count_query, "params_count": len(query_params)}, user_name=user_name)
        cur.execute(count_query, tuple(query_params))

        # Fetch the count
        row_count = cur.fetchone()[0]

        log("INFO", f"Successfully fetched row count for table '{table_name}'.", data={"row_count": row_count}, user_name=user_name)
        flush() # Flush logs after successful operation

        return jsonify({"table_name": table_name, "row_count": row_count}), 200

    except psycopg2.Error as db_error:
        log("ERROR", f"Database error while counting rows in {table_name}: {db_error}", data={"error_type": "psycopg2.Error"}, user_name=user_name)
        flush()  # Flush immediately on database errors
        return jsonify({"error": f"Database error: {db_error}"}), 500
    except Exception as e:
        log("CRITICAL", f"An unexpected error occurred while counting rows in {table_name}: {e}", data={"error_type": type(e).__name__}, user_name=user_name)
        flush()  # Flush immediately on critical unexpected errors
        return jsonify({"error": str(e)}), 500
    finally:
        if cur:
            try:
                flush() # Ensure any pending logs are flushed before closing cursor
                cur.close()
                log("INFO", "Database cursor closed.", user_name=user_name)
            except Exception as e:
                log("ERROR", f"Error closing database cursor in get_table_row_count: {e}", user_name=user_name)
                flush()
        if conn:
            try:
                conn.close()
                log("INFO", "Database connection closed.", user_name=user_name)
            except Exception as e:
                log("ERROR", f"Error closing database connection in get_table_row_count: {e}", user_name=user_name)
                flush()


if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    # Log Flask application startup details
    log("INFO", f"Flask app is starting up on port {port}.", data={"host": "0.0.0.0", "port": port})
    try:
        app.run(host="0.0.0.0", port=port, debug=True) # remove debug=True for production
    except Exception as e:
        # Log critical error if app fails to start
        log("CRITICAL", f"Flask app failed to start: {e}", data={"error_details": str(e)})
        flush()
    finally:
        # Log application shutdown (this might not always be reached on forceful termination)
        log("INFO", "Flask app is shutting down. Flushing remaining logs.")
        flush()
