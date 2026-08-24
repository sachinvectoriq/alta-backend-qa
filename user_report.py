import psycopg2
import os
from flask import Flask, request, jsonify
from logging_config import log, flush
import datetime
from dotenv import load_dotenv
import pandas as pd
from io import BytesIO
from flask import send_file

load_dotenv()

app = Flask(__name__)

# --- Configuration from Environment Variables ---
DB_CONFIG = {
    'dbname': os.getenv('DB_NAME'),
    'user': os.getenv('DB_USER'),
    'password': os.getenv('DB_PASSWORD'),
    'host': os.getenv('DB_HOST'),
    'port': os.getenv('DB_PORT')
}

# List of users to exclude from the results
EXCLUDED_USERS = [
    'Vinayak Inamadar', 'Chanbasava Koti', 'Sherlock5', 'Sachin Bhusanurmath',
    'Dinesh Rout', 'Santosh Sohani', 'Bharatkumar Salalli', 'Vinayak Inamadhar',
    'Harsh Aneppanavar', 'test', 'test1', 'test2', 'test3', 'test4', 'test5', 'Test User', 'test6', 'test7',
    'postman_test_user', 'test_user', 'John Doe', 'Chanbasav Koti','Raqib Rasheed', 'undefined', 'test_user123', 'Sherlock', 'Sherlock3', 'Sherlock2', 'Sherlock4'
]

# Define sortable columns for the outer query
SORTABLE_COLS = {
    'user': 'Employee_name',
    'first_access': 'Earliest_login_date',
    'latest_access': 'Last_login_date',
    'access_count': 'access_count',
    'domain_name': 'domain_name'
}


def validate_bearer_token(request, expected_token, user_name: str = None):
    """
    Validates the Bearer token from the Authorization header in the request.
    Returns an error response (jsonify, status_code) if invalid; otherwise, returns None.
    """
    auth_header = request.headers.get('Authorization', '')
    log("INFO", "Attempting to validate Bearer token.", data={"auth_header_present": bool(auth_header)},
        user_name=user_name)

    parts = auth_header.split(' ')
    if not auth_header.startswith('Bearer ') or len(parts) != 2:
        log("WARNING", "Invalid or missing Authorization header format.", data={"auth_header": auth_header},
            user_name=user_name)
        flush()
        return jsonify({"error": "Invalid or missing Authorization header."}), 401

    token = parts[1]

    if token != expected_token:
        log("ERROR", "Unauthorized access attempt: Invalid Bearer token.",
            data={"provided_token_prefix": token[:5] + "..."}, user_name=user_name)
        flush()
        return jsonify({"error": "Unauthorized. Invalid Bearer token."}), 403

    log("INFO", "Bearer token validated successfully.", user_name=user_name)
    flush()
    return None


@app.route('/user_login_report', methods=['GET'])
def get_user_login_report():
    """
    Fetches user login details with first/latest access dates and total access count.
    Supports filtering, dynamic sorting, and pagination via query parameters.
    """
    user_name = request.args.get('user_name', None)
    log("INFO", "API endpoint to get user login report accessed.", user_name=user_name)

    # 1. Validate Bearer Token
    auth_error = validate_bearer_token(request, 'A7x!G2p@Q9#L', user_name)
    if auth_error:
        return auth_error

    # 2. Get Filters, Pagination, and Sorting from Query Parameters
    user_filter = request.args.get('user')
    first_access_filter = request.args.get('earliest_login_date')
    latest_access_filter_start = request.args.get('last_login_date_start')
    latest_access_filter_end = request.args.get('last_login_date_end')
    limit_str = request.args.get('limit')
    pageno_str = request.args.get('page')
    sort_by = request.args.get('sort_by', 'first_access')  # Default sort column
    export_str = request.args.get('export','0')
    export=int(export_str)
    domain_name= request.args.get('domain_name',False)

    limit = 100
    page = 1
    offset = 0
    try:
        if limit_str:
            limit = int(limit_str)
            if limit <= 0: raise ValueError("Limit must be a positive integer.")
        if pageno_str:
            page = int(pageno_str)
            if page <= 0: raise ValueError("Page number must be a positive integer.")
        offset = (page - 1) * limit
        log("INFO", f"Parsed pagination: page={page}, offset={offset}", user_name=user_name)
    except ValueError as e:
        log("WARNING", f"Invalid pagination parameter. Error: {e}",
            data={"limit_str": limit_str, "pageno_str": pageno_str}, user_name=user_name)
        flush()
        return jsonify({"error": f"Invalid pagination parameter: {e}"}), 400

    conn = None
    cur = None
    try:
        log("INFO", "Attempting to connect to database to fetch user login report.", user_name=user_name)
        conn = psycopg2.connect(**DB_CONFIG)
        cur = conn.cursor()

        # 3. Construct the nested SQL query string and parameter lists
        inner_query = """
            SELECT 
                "user" AS Employee_name,
                MIN(login_date_and_time) AS Earliest_login_date,
                MAX(login_date_and_time) AS Last_login_date,
                COUNT(*) AS access_count,
                domain_name AS opco
            FROM 
                public.user_login_log
        """
        inner_where_conditions = []
        inner_query_params = []

        # Inner WHERE conditions
        inner_where_conditions.append('"user" IS NOT NULL')
        if EXCLUDED_USERS:
            placeholders = ', '.join(['%s'] * len(EXCLUDED_USERS))
            inner_where_conditions.append(f'"user" NOT IN ({placeholders})')
            inner_query_params.extend(EXCLUDED_USERS)
            log("INFO", f"Excluding {len(EXCLUDED_USERS)} users from login report.", user_name=user_name)

        if user_filter:
            inner_where_conditions.append('"user" = %s')
            inner_query_params.append(user_filter)
            log("INFO", f"Filtering by user: {user_filter}", user_name=user_name)

        if inner_where_conditions:
            inner_query += " WHERE " + " AND ".join(inner_where_conditions)

        inner_query += ' GROUP BY "user", domain_name'

        # Outer query for filtering (based on aggregated data)
        outer_query_base = f"""
            SELECT employee_name, earliest_login_date, last_login_date, access_count, opco FROM ({inner_query}) AS login_aggregates
        """
        outer_where_conditions = []
        outer_query_params = []

        # Outer WHERE conditions (date filters)
        if first_access_filter:
            try:
                if first_access_filter:
                    first_access_date = datetime.datetime.strptime(first_access_filter, '%Y-%m-%d').date()
                    outer_where_conditions.append("login_aggregates.Earliest_login_date::date >= %s")
                    outer_query_params.append(first_access_date)
                    log("INFO", f"Filtering by earliest access date >= {first_access_date}", user_name=user_name)


            except ValueError:
                log("WARNING", f"Invalid first_access date format: {first_access_filter}", user_name=user_name)
                flush()
                return jsonify({"error": "Invalid first_access date format. Use YYYY-MM-DD."}), 400

        if latest_access_filter_start or latest_access_filter_end:

            if latest_access_filter_start:
                try:
                    latest_access_date_start = datetime.datetime.strptime(latest_access_filter_start, '%Y-%m-%d').date()
                    outer_where_conditions.append("login_aggregates.Last_login_date::date >= %s")
                    outer_query_params.append(latest_access_date_start)
                    log("INFO", f"Filtering by latest access date >= {latest_access_date_start}", user_name=user_name)
                    print(latest_access_filter_start)
                    print(outer_where_conditions,outer_query_params)
                except ValueError:
                    log("WARNING", f"Invalid latest_access date format: {latest_access_filter_start}", user_name=user_name)
                    flush()
                    return jsonify({"error": "Invalid latest_access date format. Use YYYY-MM-DD."}), 400

            if latest_access_filter_end:
                try:
                    latest_access_date_end = datetime.datetime.strptime(latest_access_filter_end, '%Y-%m-%d').date()
                    outer_where_conditions.append("login_aggregates.Last_login_date::date <= %s")
                    outer_query_params.append(latest_access_date_end)
                    log("INFO", f"Filtering by latest access date <= {latest_access_date_end}", user_name=user_name)
                except ValueError:
                    log("WARNING", f"Invalid latest_access date format: {latest_access_filter_end}", user_name=user_name)
                    flush()
                    return jsonify({"error": "Invalid latest_access date format. Use YYYY-MM-DD."}), 400

        if domain_name:
            outer_where_conditions.append("login_aggregates.opco = %s")
            outer_query_params.append(domain_name)

        if outer_where_conditions:
            outer_query_base += " WHERE " + " AND ".join(outer_where_conditions)
        else:
            log("INFO", "No date filters applied.", user_name=user_name)

        # 4. Get total row count
        count_params = inner_query_params + outer_query_params
        count_query = f"SELECT COUNT(*) FROM ({outer_query_base}) AS count_query_alias"
        cur.execute(count_query, tuple(count_params))
        total_rows = cur.fetchone()[0]
        log("INFO", f"Total matching rows for report: {total_rows}", user_name=user_name)

        # 5. Handle sorting and pagination for the main query
        sort_column = SORTABLE_COLS.get(sort_by, 'Last_login_date')
        if sort_column not in SORTABLE_COLS.values():
            sort_column = 'Last_login_date'  # Fallback to default if invalid

        final_query = f"{outer_query_base} ORDER BY {sort_column} DESC LIMIT %s OFFSET %s"
        final_params = count_params + [limit, offset]

        # 6. Execute and fetch results
        log("INFO", "Executing final query for document data.",
            data={"sort_by": sort_column, "limit": limit, "offset": offset}, user_name=user_name)
        cur.execute(final_query, tuple(final_params))

        column_names = [desc[0] for desc in cur.description]
        login_records = []
        for row in cur.fetchall():
            record = dict(zip(column_names, row))
            if isinstance(record.get('Earliest_login_date'), datetime.datetime):
                record['Earliest_login_date'] = record['Earliest_login_date'].isoformat()
            if isinstance(record.get('Last_login_date'), datetime.datetime):
                record['Last_login_date'] = record['Last_login_date'].isoformat()
            login_records.append(record)

        if export==1:
            df = pd.DataFrame(rows, columns=column_names)

# 3. Save to an Excel file in memory (BytesIO) to return it without saving to disk
            output = BytesIO()
            with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                df.to_excel(writer, index=False, sheet_name='Sheet1')
            output.seek(0)
            return send_file(output, download_name="user_report.xlsx", as_attachment=True)

        log("INFO", f"Successfully fetched {len(login_records)} user login records.",
            data={"records_count": len(login_records)}, user_name=user_name)
        flush()
        return jsonify({'data': login_records, 'total_rows': total_rows}), 200

    except psycopg2.Error as db_error:
        log("ERROR", f"Database error while fetching user login report: {db_error}",
            data={"error_type": "psycopg2.Error"}, user_name=user_name)
        flush()
        return jsonify({"error": f"Database error: {db_error}"}), 500
    except Exception as e:
        log("CRITICAL", f"An unexpected error occurred while fetching user login report: {e}",
            data={"error_type": type(e).__name__}, user_name=user_name)
        flush()
        return jsonify({"error": str(e)}), 500
    finally:
        if cur:
            try:
                cur.close()
                log("INFO", "Database cursor closed.", user_name=user_name)
            except Exception as e:
                log("ERROR", f"Error closing database cursor in get_user_login_report: {e}", user_name=user_name)
                flush()
        if conn:
            try:
                conn.close()
                log("INFO", "Database connection closed.", user_name=user_name)
            except Exception as e:
                log("ERROR", f"Error closing database connection in get_user_login_report: {e}", user_name=user_name)
                flush()


# --- Main execution block remains unchanged ---
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    log("INFO", f"user report Starting Flask application on port {port}.", user_name=None)
    flush()
    try:
        app.run(host='0.0.0.0', port=port)
    except Exception as e:
        log("CRITICAL", f"user report Flask application failed to start: {e}", user_name=None, data={"error_details": str(e)})
        flush()
    finally:
        log("INFO", "user report Flask application is shutting down.", user_name=None)
        flush()
