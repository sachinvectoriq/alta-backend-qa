import psycopg2
import os
from flask import Flask, request, jsonify
from logging_config import log, flush  # Commented out: Import log and flush functions
import datetime

app = Flask(__name__)

DB_CONFIG = {
    'dbname': os.getenv('DB_NAME'),
    'user': os.getenv('DB_USER'),
    'password': os.getenv('DB_PASSWORD'),
    'host': os.getenv('DB_HOST'),
    'port': os.getenv('DB_PORT')
}

# List of users to exclude from the results for relevant tables
EXCLUDED_USERS = [
    'Vinayak Inamadar', 'Chanbasava Koti', 'Sherlock5', 'Sachin Bhusanurmath',
    'Dinesh Rout', 'Santosh Sohani', 'Bharatkumar Salalli', 'Vinayak Inamadhar',
    'Harsh Aneppanavar', 'test', 'test1', 'test2', 'test3', 'test4', 'test5', 'Test User', 'test6', 'test7',
    'postman_test_user','test_user','John Doe', 'Chanbasav Koti','Raqib Rasheed', 'undefined', 'test_user123', 'Sherlock', 'Sherlock3', 'Sherlock2', 'Sherlock4'
]

# Define filterable columns for contextsense_data_report
# This maps query parameter names to actual database column names (including aliases for joined table)
CONTEXTSENSE_FILTERABLE_COLS = {
    'modifier_type': 'T1.modifier_type',
    'modifier_value': 'T1.modifier_value',
    'user': 'T2.user',
    'source_language': 'T2.source_language',
    'target_language': 'T2.target_language',
    'character_count': 'T2.character_count',
    'vendor': 'T2.vendor',
    'domain_name':'domain_name'
}


def validate_bearer_token(request, expected_token, user_name: str = None):
    """
    Validates the Bearer token from the Authorization header in the request.
    Returns an error response (jsonify, status_code) if invalid; otherwise, returns None.
    """
    auth_header = request.headers.get('Authorization', '')
    # log("INFO", "Attempting to validate Bearer token.", data={"auth_header_present": bool(auth_header)}, user_name=user_name)
    print(f"INFO: Attempting to validate Bearer token. Auth header present: {bool(auth_header)}")

    parts = auth_header.split(' ')
    if not auth_header.startswith('Bearer ') or len(parts) != 2:
        # log("WARNING", "Invalid or missing Authorization header format.", data={"auth_header": auth_header}, user_name=user_name)
        print(f"WARNING: Invalid or missing Authorization header format. Header: '{auth_header}'")
        # flush() # Flush immediately on warning
        return jsonify({"error": "Invalid or missing Authorization header."}), 401

    token = parts[1]

    if token != expected_token:
        # log("ERROR", "Unauthorized access attempt: Invalid Bearer token.", data={"provided_token_prefix": token[:5] + "..."}, user_name=user_name)
        print(f"ERROR: Unauthorized access attempt: Invalid Bearer token. Provided token prefix: {token[:5]}...")
        # flush() # Flush immediately on error
        return jsonify({"error": "Unauthorized. Invalid Bearer token."}), 403

    # log("INFO", "Bearer token validated successfully.", user_name=user_name)
    print("INFO: Bearer token validated successfully.")
    # flush() # Flush after successful validation
    return None


@app.route('/contextsense_data_report',methods=['GET'])  # Changed route to /api/contextsense_data_report for consistency
def get_contextsense_data_report():
    """
    Fetches contextsense data with joined user_text_trans_log information.
    Supports optional date filtering, user exclusion, limit, and page number.
    Supports dynamic filtering by other column names provided as query parameters.
    Returns the fetched data as a JSON array.
    Requires Bearer token authentication.
    """
    user_name = request.args.get('user_name', 'anonymous')
    log("INFO", "API endpoint to get contextsense data report accessed.", user_name=user_name)
    print(f"INFO: API endpoint to get contextsense data report accessed by user: {user_name}")

    # 1. Validate Bearer Token
    auth_error = validate_bearer_token(request, 'A7x!G2p@Q9#L', user_name)
    if auth_error:
        return auth_error

    # 2. Get Date Filters and Pagination from Query Parameters
    start_date_str = request.args.get('start_date')
    end_date_str = request.args.get('end_date')
    pageno_str = request.args.get('page')
    limit_str = request.args.get('limit')
    domain_name = request.args.get('domain_name',False)

    start_date = None
    end_date = None
    limit = 100  # Default limit
    page = 1  # Default page
    offset = 0

    try:
        if limit_str:
            limit = int(limit_str)
            if limit <= 0:
                raise ValueError("Limit must be a positive integer.")
        log("INFO", f"Parsed limit: {limit}", user_name=user_name)
        print(f"INFO: Parsed limit: {limit}")
    except ValueError as e:
        log("WARNING", f"Invalid limit parameter: {limit_str}. Error: {e}", user_name=user_name)
        print(f"WARNING: Invalid limit parameter: {limit_str}. Error: {e}")
        flush() # Flush immediately on warning
        return jsonify({"error": f"Invalid limit parameter: {limit_str}. Must be a positive integer."}), 400

    try:
        if pageno_str:
            page = int(pageno_str)
            if page <= 0:
                raise ValueError("Page number must be a positive integer.")
        offset = (page - 1) * limit
        log("INFO", f"Parsed pagination: page={page}, offset={offset}", user_name=user_name)
        print(f"INFO: Parsed pagination: page={page}, offset={offset}")
    except ValueError as e:
        log("WARNING", f"Invalid page parameter: {pageno_str}. Error: {e}", user_name=user_name)
        print(f"WARNING: Invalid page parameter: {pageno_str}. Error: {e}")
        flush() # Flush immediately on warning
        return jsonify({"error": f"Invalid page parameter: {pageno_str}. Must be a positive integer."}), 400

    if start_date_str:
        try:
            start_date = datetime.datetime.strptime(start_date_str, '%Y-%m-%d').date()
            log("INFO", f"Parsed start_date: {start_date}", user_name=user_name)
            print(f"INFO: Parsed start_date: {start_date}")
        except ValueError:
            log("WARNING", f"Invalid start_date format: {start_date_str}", user_name=user_name)
            print(f"WARNING: Invalid start_date format: {start_date_str}")
            flush() # Flush immediately on warning
            return jsonify({"error": "Invalid start_date format. Use YYYY-MM-DD."}), 400

    if end_date_str:
        try:
            end_date = datetime.datetime.strptime(end_date_str, '%Y-%m-%d').date()
            end_date = datetime.datetime.combine(end_date, datetime.time(23, 59, 59))
            log("INFO", f"Parsed end_date: {end_date}", user_name=user_name)
            print(f"INFO: Parsed end_date: {end_date}")
        except ValueError:
            log("WARNING", f"Invalid end_date format: {end_date_str}", user_name=user_name)
            print(f"WARNING: Invalid end_date format: {end_date_str}")
            flush() # Flush immediately on warning
            return jsonify({"error": "Invalid end_date format. Use YYYY-MM-DD."}), 400

    if start_date and end_date and start_date > end_date.date():
        log("WARNING", "start_date cannot be after end_date.", user_name=user_name)
        print("WARNING: start_date cannot be after end_date.")
        flush() # Flush immediately on warning
        return jsonify({"error": "start_date cannot be after end_date."}), 400

    conn = None
    cur = None

    try:
        log("INFO", "Attempting to connect to database to fetch contextsense data.", user_name=user_name)
        print("INFO: Attempting to connect to database to fetch contextsense data.")
        conn = psycopg2.connect(**DB_CONFIG)
        cur = conn.cursor()

        # 4. Construct the SQL Query for contextsense with join
        query = """
            SELECT T1.modifier_type, T1.modifier_value, T1.system_prompt, T1.user_prompt, T1.refined_text,
                   T1.explanation, T2.user, T2.source_text, T2.translated_text, T2.source_language,
                   T2.target_language, T2.character_count, T2.vendor, T2.date_and_time, T1.domain_name
            FROM public.contextsense T1
            INNER JOIN public.user_text_trans_log T2
            ON T1.log_id=T2.log_id
        """
        query1='''SELECT COUNT(*)
            FROM public.contextsense T1
            INNER JOIN public.user_text_trans_log T2
            ON T1.log_id=T2.log_id'''
        query_conditions = []
        query_params = []

        # Add date conditions (referencing T2.date_and_time)
        if start_date:
            query_conditions.append("T2.date_and_time >= %s")
            query_params.append(start_date)
        if end_date:
            query_conditions.append("T2.date_and_time <= %s")
            query_params.append(end_date)

        # Add user exclusion condition (referencing T2.user)
        if EXCLUDED_USERS:
            placeholders = ', '.join(['%s'] * len(EXCLUDED_USERS))
            query_conditions.append(f"T2.user NOT IN ({placeholders})")
            query_params.extend(EXCLUDED_USERS)
            log("INFO", f"Applying user exclusion for contextsense data using T2.user.", data={"excluded_users_count": len(EXCLUDED_USERS)}, user_name=user_name)
            print(f"INFO: Applying user exclusion for contextsense data using T2.user.")
            log("INFO", f"Query parameters (including excluded users): {query_params}", user_name=user_name) # Too verbose

        if domain_name:
            query_conditions.append("domain=%s")
            query_params.extend(domain_name)

        # Add dynamic column filters
        for param_key, param_value in request.args.items():
            # Skip parameters already handled (date, pagination, user_name)
            if param_key in ['start_date', 'end_date', 'limit', 'page', 'user_name']:
                continue

            # Check if the parameter key is a valid filterable column for this table
            if param_key in CONTEXTSENSE_FILTERABLE_COLS:
                db_column = CONTEXTSENSE_FILTERABLE_COLS[param_key]
                # Special handling for integer types
                if param_key == 'character_count':
                    try:
                        int_value = int(param_value)
                        query_conditions.append(f"{db_column} = %s")
                        query_params.append(int_value)
                        print(f"INFO: Added integer filter: {param_key}={int_value}")
                    except ValueError:
                        print(f"WARNING: Invalid integer value for {param_key}: {param_value}")
                        return jsonify({"error": f"Invalid value for {param_key}. Must be an integer."}), 400
                else:
                    # For other string-based columns, use exact match
                    query_conditions.append(f"{db_column} = %s")
                    query_params.append(param_value)
                    print(f"INFO: Added string filter: {param_key}={param_value}")
            else:
                print(f"WARNING: Ignoring unrecognized query parameter for filtering: {param_key}")

        # Combine all conditions
        if query_conditions:
            query += " WHERE " + " AND ".join(query_conditions)
            query1 += " WHERE " + " AND ".join(query_conditions)

        # Add ORDER BY clause as specified
        query += " ORDER BY T1.selection_id ASC"

        row_count=0

        cur.execute(query1, tuple(query_params))
        row_count = cur.fetchone()[0]

        # Add LIMIT and OFFSET for pagination
        query += " LIMIT %s OFFSET %s"
        query_params.extend([limit, offset])

        log("INFO", f"Executing query for contextsense data.", data={"query": query, "params_count": len(query_params)}, user_name=user_name)
        print(f"INFO: Executing query for contextsense data: {query}")
        print(f"INFO: Query parameters: {query_params}")
        cur.execute(query, tuple(query_params))

        # Fetch results
        column_names = [desc[0] for desc in cur.description]
        records = []
        for row in cur.fetchall():
            records.append(dict(zip(column_names, row)))

        log("INFO", f"Successfully fetched {len(records)} contextsense records.", data={"records_count": len(records)}, user_name=user_name)
        print(f"INFO: Successfully fetched {len(records)} contextsense records.")
        flush() # Flush after successful operation
        return jsonify({'data': records,'total_rows': row_count}), 200
    except psycopg2.Error as db_error:
        log("ERROR", f"Database error while fetching contextsense data: {db_error}", data={"error_type": "psycopg2.Error"}, user_name=user_name)
        print(f"ERROR: Database error while fetching contextsense data: {db_error}")
        flush() # Flush immediately on database errors
        return jsonify({"error": f"Database error: {db_error}"}), 500
    except Exception as e:
        log("CRITICAL", f"An unexpected error occurred while fetching contextsense data: {e}", data={"error_type": type(e).__name__}, user_name=user_name)
        print(f"CRITICAL: An unexpected error occurred while fetching contextsense data: {e}")
        flush() # Flush immediately on critical unexpected errors
        return jsonify({"error": str(e)}), 500
    finally:
        if cur:
            try:
                flush() # Ensure any pending logs are flushed before closing cursor
                cur.close()
                log("INFO", "Database cursor closed.", user_name=user_name)
                print("INFO: Database cursor closed.")
            except Exception as e:
                log("ERROR", f"Error closing database cursor in get_contextsense_data_report: {e}", user_name=user_name)
                print(f"ERROR: Error closing database cursor in get_contextsense_data_report: {e}")
                flush()
        if conn:
            try:
                conn.close()
                log("INFO", "Database connection closed.", user_name=user_name)
                print("INFO: Database connection closed.")
            except Exception as e:
                log("ERROR", f"Error closing database connection in get_contextsense_data_report: {e}", user_name=user_name)
                print(f"ERROR: Error closing database connection in get_contextsense_data_report: {e}")
                flush()


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    log("INFO", f"Starting contextsense_report Flask application on port {port}.", user_name=None) # Using None for startup
    flush()
    try:
        app.run(host='0.0.0.0', port=port)
    except Exception as e:
        log("CRITICAL", f"contextsense_report Flask application failed to start: {e}", user_name=None, data={"error_details": str(e)}) # Using None for critical startup error
        flush()
    finally:
        log("INFO", "contextsense_report Flask application is shutting down.", user_name=None) # Using None for shutdown
        flush()

