import psycopg2
import os
from flask import Flask, request, jsonify, send_file
#from logging_config import log, flush
import datetime
import pandas as pd  # Import pandas for DataFrame and Excel export
import io  # Import io for BytesIO
import dotenv
from dotenv import load_dotenv

load_dotenv()

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
    'contextsense',
    'user_docu_trans_log',
    'user_text_trans_log',
    'user_login_log'
]

# List of users to exclude from the results for relevant tables
EXCLUDED_USERS = [
    'Vinayak Inamadar', 'Chanbasava Koti', 'Sherlock5', 'Sachin Bhusanurmath',
    'Dinesh Rout', 'Santosh Sohani', 'Bharatkumar Salalli', 'Vinayak Inamadhar',
    'Harsh Aneppanavar', 'test', 'test1', 'test2', 'test3', 'test4', 'test5', 'Test User', 'test6', 'test7',
    'postman_test_user', 'test_user', 'John Doe', 'Chanbasav Koti','Raqib Rasheed', 'undefined', 'test_user123', 'Sherlock', 'Sherlock3', 'Sherlock2', 'Sherlock4'
]


def validate_bearer_token(request, expected_token, user_name: str = None):
    """
    Validates the Bearer token from the Authorization header in the request.
    Returns an error response (jsonify, status_code) if invalid; otherwise, returns None.
    """
    auth_header = request.headers.get('Authorization', '')
    #log("INFO", "Attempting to validate Bearer token.", data={"auth_header_present": bool(auth_header)},
        #user_name=user_name)

    parts = auth_header.split(' ')
    if not auth_header.startswith('Bearer ') or len(parts) != 2:
        #log("WARNING", "Invalid or missing Authorization header format.", data={"auth_header": auth_header},user_name=user_name)
        #flush()  # Flush immediately on warning
        return jsonify({"error": "Invalid or missing Authorization header."}), 401

    token = parts[1]

    if token != expected_token:
        #log("ERROR", "Unauthorized access attempt: Invalid Bearer token.",data={"provided_token_prefix": token[:5] + "..."}, user_name=user_name)
        #flush()  # Flush immediately on error
        return jsonify({"error": "Unauthorized. Invalid Bearer token."}), 403

    #log("INFO", "Bearer token validated successfully.", user_name=user_name)
    #flush()  # Flush after successful validation
    return None


@app.route('/export_table_data', methods=['GET'])
def export_table_data():
    """
    Fetches all rows from a specified table, excluding specific users,
    and returns the data as an Excel file.
    Requires 'table_name' as a query parameter.
    Requires Bearer token authentication.
    """
    user_name = request.args.get('user_name', None)
    table_name = request.args.get('table_name')

    #log("INFO", "API endpoint to export table data accessed.", data={"table_name": table_name}, user_name=user_name)

    # 1. Validate Bearer Token
    auth_error = validate_bearer_token(request, 'A7x!G2p@Q9#L', user_name)
    if auth_error:
        return auth_error

    # 2. Validate table_name for security
    if not table_name:
        #log("WARNING", "'table_name' query parameter is missing.", user_name=user_name)
        #flush()
        return jsonify({"error": "Missing 'table_name' query parameter."}), 400

    if table_name not in ALLOWED_TABLES:
        #log("WARNING", f"Attempt to access unauthorized table: {table_name}", data={"allowed_tables": ALLOWED_TABLES},user_name=user_name)
        #flush()
        return jsonify({"error": "Unauthorized table name."}), 403

    conn = None
    cur = None

    try:
        #log("INFO", f"Attempting to connect to database to fetch data from table: {table_name}.", user_name=user_name)
        conn = psycopg2.connect(**DB_CONFIG)
        cur = conn.cursor()

        query_conditions = []
        query_params = []

        placeholders = ', '.join(['%s'] * len(EXCLUDED_USERS))

        # Add user exclusion condition based on table name
        if EXCLUDED_USERS:
            if table_name == 'user_text_trans_log':
                query_conditions.append(f"user_text_trans_log.user NOT IN ({placeholders})")
                query_params.extend(EXCLUDED_USERS)
            elif table_name == 'user_docu_trans_log':
                query_conditions.append(f"user_docu_trans_log.user NOT IN ({placeholders})")
                query_params.extend(EXCLUDED_USERS)
            elif table_name == 'user_login_log':
                query_conditions.append(f"user_login_log.user NOT IN ({placeholders})")
                query_params.extend(EXCLUDED_USERS)
            elif table_name == 'contextsense':
                query_conditions.append(f"T2.user NOT IN ({placeholders})")
                query_params.extend(EXCLUDED_USERS)

        # Construct the base query
        if table_name == 'contextsense':
            query = f"""
                SELECT T2.user, T1.modifier_type, T1.modifier_value, T1.system_prompt, T1.user_prompt, T1.refined_text,
                       T1.explanation, T2.source_text, T2.translated_text, T2.source_language,
                       T2.target_language, T2.character_count, T2.vendor, T2.date_and_time
                FROM public.contextsense T1
                INNER JOIN public.user_text_trans_log T2
                ON T1.log_id=T2.log_id
            """
        elif table_name == 'user_text_trans_log':
            query = "SELECT user_text_trans_log.user, source_text, translated_text, source_language, target_language, character_count, vendor, date_and_time, refinement_used FROM public.user_text_trans_log"
        elif table_name == 'user_docu_trans_log':
            query = "SELECT user_docu_trans_log.user, document_name, source_language, target_language, character_count, vendor, date_and_time FROM public.user_docu_trans_log"
        elif table_name == 'user_login_log':
            query = """SELECT user_login_log.user AS Employee_name, MIN(login_date_and_time) AS Earliest_login_date, MAX(login_date_and_time) AS Last_login_date
            FROM public.user_login_log"""
        else:
            query = f"SELECT * FROM public.{table_name}"
            #log("WARNING", f"Using generic SELECT * for table: {table_name}", user_name=user_name)

        # Append WHERE clause if conditions exist
        if query_conditions:
            query += " WHERE " + " AND ".join(query_conditions)
            #log("INFO", f"Applied WHERE clause to query for table: {table_name}.", user_name=user_name)

        #log("INFO", f"Executing query for table export.", data={"query": query, "params_count": len(query_params)},user_name=user_name)
        if table_name== 'user_login_log':
            query += "GROUP BY user_login_log.user"
        cur.execute(query, tuple(query_params))

        column_names = [desc[0] for desc in cur.description]
        records = cur.fetchall()

        #log("INFO", f"Successfully fetched {len(records)} records from table: {table_name} for export.",data={"records_count": len(records)}, user_name=user_name)

        # Create a Pandas DataFrame
        df = pd.DataFrame(records, columns=column_names)

        # --- START OF FIX FOR TIMEZONE AWARE DATETIMES ---
        #log("INFO", "Checking for timezone-aware datetimes to localize for Excel compatibility.", user_name=user_name)
        for col in df.columns:
            # This check is robust for any timezone-aware datetime column
            if isinstance(df[col].dtype, pd.DatetimeTZDtype):
                #log("INFO", f"Localizing timezone-aware datetime column: '{col}'", user_name=user_name)
                # Remove timezone information from the datetime objects
                df[col] = df[col].dt.tz_localize(None)

        # Create an in-memory binary stream
        output = io.BytesIO()
        df.to_excel(output, index=False, engine='xlsxwriter')
        output.seek(0)

        #log("INFO", f"Successfully prepared Excel file for table {table_name}.", user_name=user_name)
        #flush()

        return send_file(
            output,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            download_name=f'{table_name}_report.xlsx',
            as_attachment=True
        )

    except psycopg2.Error as db_error:
        #log("ERROR", f"Database error while fetching data from {table_name}: {db_error}",data={"error_type": "psycopg2.Error"}, user_name=user_name)
        #flush()
        return jsonify({"error": f"Database error: {db_error}"}), 500
    except Exception as e:
        #log("CRITICAL", f"An unexpected error occurred while exporting data from {table_name}: {e}",data={"error_type": type(e).__name__}, user_name=user_name)
        #flush()
        return jsonify({"error": str(e)}), 500
    finally:
        if cur:
            cur.close()

        if conn:
            conn.close()
                #log("INFO", "Database connection closed.", user_name=user_name)


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    #log("INFO", f"Starting Flask Export report application on port {port}.", user_name=None)
    #flush()
    app.run(host='0.0.0.0', port=port)






