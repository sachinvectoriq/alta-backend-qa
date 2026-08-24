from flask import Flask, request, jsonify
import psycopg2
import os
from typing import Optional, Any, Tuple

# Assuming logging_config.py exists and defines log and flush functions
from logging_config import log, flush

app = Flask(__name__)

def connect_db(user_name: Optional[str] = None):
    """
    Establishes a connection to the PostgreSQL database using environment variables.
    Logs connection attempts and outcomes.
    """
    host = os.getenv('DB_HOST')
    database = os.getenv('DB_NAME')
    db_user = os.getenv('DB_USER')
    password = os.getenv('DB_PASSWORD')
    port_str = os.getenv('DB_PORT')

    log("INFO", "Attempting to establish database connection for login logging.", user_name=user_name)

    if not all([host, database, db_user, password, port_str]):
        log("CRITICAL", "One or more database environment variables (DB_HOST, DB_NAME, DB_USER, DB_PASSWORD, DB_PORT) are not set.",
            data={"action": "db_connection_init_fail"}, user_name=user_name)
        flush()
        return None

    try:
        port = int(port_str)
    except (ValueError, TypeError) as e:
        log("CRITICAL", f"Invalid port number provided: '{port_str}'. Must be an integer. Error: {e}",
            data={"action": "db_connection_init_fail"}, user_name=user_name)
        flush()
        return None

    try:
        connection = psycopg2.connect(
            host=host,
            database=database,
            user=db_user,
            password=password,
            port=port
        )
        log("INFO", "Successfully connected to the database for login logging.", user_name=user_name,
            data={"db_host": host, "db_name": database, "db_user": db_user, "db_port": port})
        return connection
    except psycopg2.Error as e:
        log("ERROR", f"Error connecting to the database for login logging: {e}",
            data={"db_host": host, "db_name": database, "db_user": db_user})
        flush()
        return None

@app.route('/unique-values', methods=['GET'])
def get_unique_values():
    """
    API endpoint to fetch unique values from a specified column in a specified table.
    Requires 'table_name' and 'column_name' as query parameters.
    """
    table_name = request.args.get('table_name')
    column_name = request.args.get('column_name')

    if not table_name or not column_name:
        log("WARNING", "Missing table_name or column_name in request parameters.", data={"action": "unique_values_request_fail"})
        return jsonify({"error": "Missing 'table_name' or 'column_name' query parameter"}), 400

    conn = None
    cursor = None
    try:
        conn = connect_db()
        if conn is None:
            return jsonify({"error": "Could not connect to the database"}), 503

        cursor = conn.cursor()
        
        # Use psycopg2.sql to safely inject table and column names into the query
        from psycopg2 import sql
        query = sql.SQL("SELECT DISTINCT {col} FROM {tbl}").format(
            col=sql.Identifier(column_name),
            tbl=sql.Identifier(table_name)
        )
        
        log("INFO", f"Executing query to fetch unique values for column {column_name} in table {table_name}.")
        cursor.execute(query)
        
        results = cursor.fetchall()
        
        # Format results into a list
        unique_values = [item[0] for item in results]

        log("INFO", f"Successfully fetched {len(unique_values)} unique values.")
        return jsonify({"table": table_name, "column": column_name, "unique_values": unique_values})

    except psycopg2.errors.UndefinedTable as e:
        log("ERROR", f"Database error: Table '{table_name}' does not exist. Error: {e}", data={"action": "db_query_fail"})
        return jsonify({"error": f"Table '{table_name}' does not exist"}), 404
    except psycopg2.errors.UndefinedColumn as e:
        log("ERROR", f"Database error: Column '{column_name}' does not exist in table '{table_name}'. Error: {e}", data={"action": "db_query_fail"})
        return jsonify({"error": f"Column '{column_name}' does not exist in table '{table_name}'"}), 404
    except psycopg2.Error as e:
        log("ERROR", f"Database error while fetching unique values: {e}", data={"action": "db_query_fail"})
        return jsonify({"error": f"Database error: {e}"}), 500
    except Exception as e:
        log("CRITICAL", f"An unexpected error occurred: {e}", data={"action": "unexpected_error"})
        return jsonify({"error": "An unexpected server error occurred"}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()
            log("INFO", "Database connection closed.")

if __name__ == '__main__':
    # Ensure environment variables are set before running the app
    if not all(os.getenv(var) for var in ['DB_HOST', 'DB_NAME', 'DB_USER', 'DB_PASSWORD', 'DB_PORT']):
        log("CRITICAL", "One or more database environment variables are not set. Cannot run the Flask app.")
        flush()
    else:
        # Run the app. Consider using a production server like Gunicorn in a real deployment.
        app.run(debug=True)
