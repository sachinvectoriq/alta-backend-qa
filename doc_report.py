import psycopg2
import os
from flask import Flask, request, jsonify
#from logging_config import log, flush  # Commented out: Import log and flush functions
import datetime
import pandas as pd
from io import BytesIO
from flask import send_file

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
    'postman_test_user','test_user','John Doe'
]

# Define filterable columns for user_docu_trans_log
DOC_TRANS_FILTERABLE_COLS = {
    'user': 'user_docu_trans_log.user',
    'document_name': 'document_name',
    'source_language': 'source_language',
    'target_language': 'target_language',
    'billed_characters': 'billed_characters',
    'vendor': 'vendor',
    'domain_name':'domain_name'
}

order_dict = {
    "user": "user",
    "doc": "document_name",
    "from_lang": "source_language",
    "to_lang": "target_language",
    "chars": "billed_characters",
    "size": "size_of_the_document",
    "vendor": "vendor",
    "timestamp": "date_and_time",
    "log_id": "log_id",
    "glossary": "glossary_filename",
    "session": "login_session_id",
    "domain_name":"domain_name"
}


def validate_bearer_token(request, expected_token, user_name: str = None):
    """
    Validates the Bearer token from the Authorization header in the request.
    Returns an error response (jsonify, status_code) if invalid; otherwise, returns None.
    """
    auth_header = request.headers.get('Authorization', '')
    #log("INFO", "Attempting to validate Bearer token.", data={"auth_header_present": bool(auth_header)}, user_name=user_name)
    print(f"INFO: Attempting to validate Bearer token. Auth header present: {bool(auth_header)}")

    parts = auth_header.split(' ')
    if not auth_header.startswith('Bearer ') or len(parts) != 2:
        #log("WARNING", "Invalid or missing Authorization header format.", data={"auth_header": auth_header}, user_name=user_name)
        print(f"WARNING: Invalid or missing Authorization header format. Header: '{auth_header}'")
        #flush() # Flush immediately on warning
        return jsonify({"error": "Invalid or missing Authorization header."}), 401

    token = parts[1]

    if token != expected_token:
        #log("ERROR", "Unauthorized access attempt: Invalid Bearer token.", data={"provided_token_prefix": token[:5] + "..."}, user_name=user_name)
        print(f"ERROR: Unauthorized access attempt: Invalid Bearer token. Provided token prefix: {token[:5]}...")
        #flush() # Flush immediately on error
        return jsonify({"error": "Unauthorized. Invalid Bearer token."}), 403

    #log("INFO", "Bearer token validated successfully.", user_name=user_name)
    print("INFO: Bearer token validated successfully.")
    #flush() # Flush after successful validation
    return None


@app.route('/doc_data_report', methods=['GET'])
def get_doc_data_report():
    """
    Fetches user document translation data from the database.
    Supports optional date filtering, user exclusion, limit, and page number.
    Supports dynamic filtering by other column names provided as query parameters.
    Returns the fetched data as a JSON array.
    Requires Bearer token authentication.
    """
    user_name = request.args.get('user_name', None)  # Default to anonymous if not provided
    #log("INFO", "API endpoint to get doc data report accessed.", user_name=user_name)
    print(f"INFO: API endpoint to get doc data report accessed by user: {user_name}")

    # 1. Validate Bearer Token
    auth_error = validate_bearer_token(request, 'A7x!G2p@Q9#L', user_name)
    if auth_error:
        return auth_error

    # 2. Get Date Filters and Pagination from Query Parameters
    start_date_str = request.args.get('start_date')
    end_date_str = request.args.get('end_date')
    limit_str = request.args.get('limit')
    pageno_str = request.args.get('page')
    order_str = request.args.get('order','timestamp')  # Default ordering by date_and_time
    orderby_str = request.args.get('orderby','asc')  # Default ordering direction
    export_str = request.args.get('export','0')
    export=int(export_str)
    domain_name= request.args.get('domain_name',False)

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
        #log("INFO", f"Parsed limit: {limit}", user_name=user_name)
        print(f"INFO: Parsed limit: {limit}")
    except ValueError as e:
        #log("WARNING", f"Invalid limit parameter: {limit_str}. Error: {e}", user_name=user_name)
        print(f"WARNING: Invalid limit parameter: {limit_str}. Error: {e}")
        #flush()
        return jsonify({"error": f"Invalid limit parameter: {limit_str}. Must be a positive integer."}), 400

    try:
        if pageno_str:
            page = int(pageno_str)
            if page <= 0:
                raise ValueError("Page number must be a positive integer.")
        offset = (page - 1) * limit
        #log("INFO", f"Parsed pagination: page={page}, offset={offset}", user_name=user_name)
        print(f"INFO: Parsed pagination: page={page}, offset={offset}")
    except ValueError as e:
        #log("WARNING", f"Invalid page parameter: {pageno_str}. Error: {e}", user_name=user_name)
        print(f"WARNING: Invalid page parameter: {pageno_str}. Error: {e}")
        #flush()
        return jsonify({"error": f"Invalid page parameter: {pageno_str}. Must be a positive integer."}), 400

    if start_date_str:
        try:
            start_date = datetime.datetime.strptime(start_date_str, '%Y-%m-%d').date()
            #log("INFO", f"Parsed start_date: {start_date}", user_name=user_name)
            print(f"INFO: Parsed start_date: {start_date}")
        except ValueError:
            #log("WARNING", f"Invalid start_date format: {start_date_str}", user_name=user_name)
            print(f"WARNING: Invalid start_date format: {start_date_str}")
            #flush()
            return jsonify({"error": "Invalid start_date format. Use YYYY-MM-DD."}), 400

    if end_date_str:
        try:
            end_date = datetime.datetime.strptime(end_date_str, '%Y-%m-%d').date()
            # For end_date, we want to include the whole day, so set time to end of day
            end_date = datetime.datetime.combine(end_date, datetime.time(23, 59, 59))
            #log("INFO", f"Parsed end_date: {end_date}", user_name=user_name)
            print(f"INFO: Parsed end_date: {end_date}")
        except ValueError:
            #log("WARNING", f"Invalid end_date format: {end_date_str}", user_name=user_name)
            print(f"WARNING: Invalid end_date format: {end_date_str}")
            #flush()
            return jsonify({"error": "Invalid end_date format. Use YYYY-MM-DD."}), 400

    # Ensure end_date is not before start_date if both are provided
    if start_date and end_date and start_date > end_date.date():
        #log("WARNING", "start_date cannot be after end_date.", user_name=user_name)
        print("WARNING: start_date cannot be after end_date.")
        #flush()
        return jsonify({"error": "start_date cannot be after end_date."}), 400

    conn = None
    cur = None

    try:
        #log("INFO", "Attempting to connect to database to fetch document data report.", user_name=user_name)
        print("INFO: Attempting to connect to database to fetch document data report.")
        conn = psycopg2.connect(**DB_CONFIG)
        cur = conn.cursor()

        # 3. Construct SQL Query with Conditional WHERE Clause
        query = "SELECT date_and_time, document_name, source_language, target_language, user_docu_trans_log.user, vendor, billed_characters, size_of_the_document, glossary_filename, login_session_id, log_id, domain_name AS opco  FROM public.user_docu_trans_log"
        query1 = "SELECT COUNT(*) FROM public.user_docu_trans_log"
        query_conditions = []
        query_params = []

        # Add date conditions
        if start_date:
            query_conditions.append("date_and_time >= %s")
            query_params.append(start_date)
        if end_date:
            query_conditions.append("date_and_time <= %s")
            query_params.append(end_date)

        # Add user exclusion condition
        if EXCLUDED_USERS:
            placeholders = ', '.join(['%s'] * len(EXCLUDED_USERS))
            query_conditions.append(f"user_docu_trans_log.user NOT IN ({placeholders})")  # Directly use 'user' as column name
            query_params.extend(EXCLUDED_USERS)
            #log("INFO", f"Excluding {len(EXCLUDED_USERS)} users from document data report.", user_name=user_name)
            print(f"INFO: Excluding {len(EXCLUDED_USERS)} users from document data report.")
        
        if domain_name:
            query_conditions.append(f"domain_name=%s")
            query_params.extend(domain_name)

        # Add dynamic column filters
        for param_key, param_value in request.args.items():
            # Skip parameters already handled (date, pagination, user_name)
            if param_key in ['start_date', 'end_date', 'limit', 'page', 'user_name']:
                continue

            # Check if the parameter key is a valid filterable column for this table
            if param_key in DOC_TRANS_FILTERABLE_COLS:
                db_column = DOC_TRANS_FILTERABLE_COLS[param_key]
                # Special handling for integer types
                if param_key == 'billed_characters':
                    try:
                        int_value = int(param_value)
                        query_conditions.append(f"{db_column} = %s")
                        query_params.append(int_value)
                        #log("INFO", f"Added integer filter: {param_key}={int_value}", user_name=user_name)
                        print(f"INFO: Added integer filter: {param_key}={int_value}")
                    except ValueError:
                        #log("WARNING", f"Invalid integer value for {param_key}: {param_value}", user_name=user_name)
                        print(f"WARNING: Invalid integer value for {param_key}: {param_value}")
                        #flush()
                        return jsonify({"error": f"Invalid value for {param_key}. Must be an integer."}), 400
                else:
                    # For other string-based columns, use exact match
                    query_conditions.append(f"{db_column} = %s")
                    query_params.append(param_value)
                    #log("INFO", f"Added string filter: {param_key}={param_value}", user_name=user_name)
                    print(f"INFO: Added string filter: {param_key}={param_value}")
            else:
                #log("WARNING", f"Ignoring unrecognized query parameter for filtering: {param_key}", user_name=user_name)
                print(f"WARNING: Ignoring unrecognized query parameter for filtering: {param_key}")

        # Combine all conditions
        if query_conditions:
            query += " WHERE " + " AND ".join(query_conditions)
            query1 += " WHERE " + " AND ".join(query_conditions)
        else:
            #log("INFO", "Fetching all document data (no date or user filters).", user_name=user_name)
            print("INFO: Fetching all document data (no date or user filters).")
        if order_str in order_dict:
            if orderby_str.lower() not in ['asc', 'desc']:
                #log("WARNING", f"Invalid orderby parameter: {orderby_str}. Defaulting to 'asc'.", user_name=user_name)
                print(f"WARNING: Invalid orderby parameter: {orderby_str}. Defaulting to 'asc'.")
                orderby_str = 'asc'
            query += f" ORDER BY {order_dict[order_str]} {orderby_str.upper()}"
        row_count=0
        cur.execute(query1, tuple(query_params))
        row_count= cur.fetchone()[0]

        query += "  LIMIT %s OFFSET %s"  # Add ORDER BY, LIMIT, OFFSET
        query_params.extend([limit, offset])

        #log("INFO", f"Executing query for document data.", data={"query": query, "params_count": len(query_params)}, user_name=user_name)
        print(f"INFO: Executing query for document data: {query}")
        print(f"INFO: Query parameters: {query_params}")
        cur.execute(query, tuple(query_params))

        # Fetch results
        rows=cur.fetchall()
        column_names = [desc[0] for desc in cur.description]
        if export==1:
            df = pd.DataFrame(rows, columns=column_names)

# 3. Save to an Excel file in memory (BytesIO) to return it without saving to disk
            output = BytesIO()
            with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                df.to_excel(writer, index=False, sheet_name='Sheet1')
            output.seek(0)
            return send_file(output, download_name="doc_report.xlsx", as_attachment=True)
        doc_records = []
        for row in rows:
            doc_records.append(dict(zip(column_names, row)))

        #log("INFO", f"Successfully fetched {len(doc_records)} document data records.", data={"records_count": len(doc_records)}, user_name=user_name)
        print(f"INFO: Successfully fetched {len(doc_records)} document data records.")
        #flush() # Flush after successful operation
        return jsonify({'data': doc_records, 'total_rows': row_count}), 200

    except psycopg2.Error as db_error:
        # log("ERROR", f"Database error while fetching document data report: {db_error}", data={"error_type": "psycopg2.Error"}, user_name=user_name)
        print(f"ERROR: Database error while fetching document data report: {db_error}")
        # flush() # Flush immediately on database errors
        return jsonify({"error": f"Database error: {db_error}"}), 500
    except Exception as e:
        # log("CRITICAL", f"An unexpected error occurred while fetching document data report: {e}", data={"error_type": type(e).__name__}, user_name=user_name)
        print(f"CRITICAL: An unexpected error occurred while fetching document data report: {e}")
        # flush() # Flush immediately on critical unexpected errors
        return jsonify({"error": str(e)}), 500
    finally:
        if cur:
            try:
                # flush() # Ensure any pending logs are flushed before closing cursor
                cur.close()
                # log("INFO", "Database cursor closed.", user_name=user_name)
                print("INFO: Database cursor closed.")
            except Exception as e:
                # log("ERROR", f"Error closing database cursor in get_doc_data_report: {e}", user_name=user_name)
                print(f"ERROR: Error closing database cursor in get_doc_data_report: {e}")
                # flush()
        if conn:
            try:
                conn.close()
                # log("INFO", "Database connection closed.", user_name=user_name)
                print("INFO: Database connection closed.")
            except Exception as e:
                # log("ERROR", f"Error closing database connection in get_doc_data_report: {e}", user_name=user_name)
                print(f"ERROR: Error closing database connection in get_doc_data_report: {e}")
                # flush()



