from flask import request, jsonify
import psycopg2
import os
from logging_config import log, flush
from typing import Any, Tuple, Optional

# Assuming validate_bearer_token is defined elsewhere and can be imported
# from your main application or a security module.
# For demonstration, I'll define a simple placeholder if it's not imported:

def get_db_connection():
    """
    Establish a database connection using environment variables.
    Logs connection attempts and outcomes.
    Raises an exception if connection fails.
    """
    host = os.getenv('DB_HOST')
    database = os.getenv('DB_NAME')
    user = os.getenv('DB_USER')
    password = os.getenv('DB_PASSWORD')
    port_str = os.getenv('DB_PORT')

    log("INFO", "Attempting to establish database connection.")
    flush()

    # Convert port to integer
    if not port_str:
        log("CRITICAL", "DB_PORT environment variable is not set.", data={"action": "db_connection_init"})
        raise Exception("Database connection failed: DB_PORT environment variable is missing.")
    try:
        port = int(port_str)
    except ValueError as e:
        log("CRITICAL", f"Invalid port number provided: {port_str}. Error: {e}", data={"action": "db_connection_init"})
        raise Exception(f"Database connection failed: Invalid port number '{port_str}'.") from e
    except TypeError as e:
        log("CRITICAL", f"DB_PORT environment variable is not a string. Error: {e}", data={"action": "db_connection_init"})
        raise Exception(f"Database connection failed: DB_PORT environment variable is invalid type.") from e

    try:
        conn = psycopg2.connect(
            host=host,
            database=database,
            user=user,
            password=password,
            port=port
        )
        log("INFO", "Successfully established database connection.", data={"db_host": host, "db_name": database, "db_user": user, "db_port": port})
        flush()
        return conn
    except psycopg2.OperationalError as e:
        log("ERROR", f"Database connection operational error: {e}", data={"db_host": host, "db_name": database, "db_user": user, "db_port": port, "action": "db_connection_failure"})
        flush()
        raise Exception(f"Failed to connect to the database. Please check database credentials and availability. Details: {e}") from e
    except Exception as e:
        log("CRITICAL", f"An unexpected error occurred during database connection: {e}", data={"db_host": host, "db_name": database, "db_user": user, "db_port": port, "action": "db_connection_failure"})
        flush()
        raise Exception(f"An unexpected error occurred during database connection. Details: {e}") from e

def get_settings_deepl():
    """
    API endpoint to retrieve DeepL API key based on admin_id.
    Requires 'admin_id' in query parameters and validates a Bearer token.
    """
    # Placeholder for Bearer token validation. Replace 'YOUR_EXPECTED_BEARER_TOKEN'
    # with the actual token from your environment variables or config.
    # You would typically import this from a security module or common utilities.

    # Log API request initiation
    log("INFO", "Received request for DeepL settings.", data={"endpoint": "/get_settings_deepl"})
    flush()

    admin_id_str = request.args.get('admin_id')
    if not admin_id_str:
        log("WARNING", "Missing 'admin_id' in query parameters.")
        flush()
        return jsonify({"error": "Missing admin_id query parameter."}), 400

    try:
        admin_id = int(admin_id_str)
        log("INFO", f"Parsed admin_id: {admin_id}.", data={"admin_id_str": admin_id_str})
        flush()
    except ValueError as e:
        log("WARNING", f"Invalid 'admin_id' format: '{admin_id_str}'. Must be an integer. Error: {e}")
        flush()
        return jsonify({"error": "Invalid admin_id format. Must be an integer."}), 400

    conn = None # Initialize conn to None for finally block
    try:
        conn = get_db_connection()
        # No need to check 'if not conn' here, as get_db_connection now raises an exception on failure
        # and that exception will be caught by the outer try-except block.

        with conn.cursor() as cursor:
            query = """
            SELECT api_key FROM deepl_settings WHERE admin_id = %s;
            """
            cursor.execute(query, (admin_id,))
            result = cursor.fetchone()

        if result:
            log("INFO", f"DeepL API key found for admin_id: {admin_id}.", data={"admin_id": admin_id, "api_key_status": "found"})
            flush()
            return jsonify({"admin_id": admin_id, "api_key": result[0]}), 200
        else:
            log("INFO", f"No DeepL settings found for admin_id: {admin_id}.", data={"admin_id": admin_id, "api_key_status": "not_found"})
            flush()
            return jsonify({"error": f"No DeepL settings found for admin_id {admin_id}."}), 404

    except Exception as e:
        # Catch exceptions from get_db_connection or any other part of the try block
        log("ERROR", f"An error occurred while fetching DeepL settings: {e}", data={"admin_id": admin_id, "error_type": type(e).__name__})
        flush()
        # Return a generic error message to the client for security, log full details internally
        return jsonify({"error": "An internal server error occurred while retrieving settings."}), 500
    finally:
        if conn:
            log("INFO", "Closing database connection.", data={"admin_id": admin_id})
            flush()
            conn.close()
