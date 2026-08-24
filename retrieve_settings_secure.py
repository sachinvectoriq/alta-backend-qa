# retrieve_settings.py
from flask import request, jsonify
import psycopg2
import os
import logging

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


def retrieve_settings_secure():
    auth_error = validate_bearer_token(request, 'A7x!G2p@Q9#L')  # Replace 'A7x!G2p@Q9#L' with your actual token
    if auth_error:
        return auth_error

    try:
        # Extract Admin_id from the request parameters
        admin_id = request.args.get('admin_id')

        if not admin_id:
            return jsonify({"error": "Please provide an 'admin_id'."}), 400
        
        # Get connection details from environment variables
        host = os.getenv('DB_HOST')
        database = os.getenv('DB_NAME')
        user = os.getenv('DB_USER')
        password = os.getenv('DB_PASSWORD')
        port_str = os.getenv('DB_PORT')

        # Ensure all variables are set
        if not all([host, database, user, password, port_str]):
            return jsonify({"error": "Database connection details are not set properly."}), 500

        # Convert port to integer
        try:
            port = int(port_str)
        except (ValueError, TypeError) as e:
            logging.error(f"Port conversion error: {e}")
            return jsonify({"error": "Invalid port number."}), 500

        # Connect to PostgreSQL
        connection = psycopg2.connect(
            host=host,
            database=database,
            user=user,
            password=password,
            port=port
        )
        cursor = connection.cursor()

        # Query the database for the settings associated with the given Admin_id
        query = """
        SELECT key, text_translation_endpoint, document_translation_endpoint, region, storage_connection_string
        FROM settings
        WHERE admin_id = %s;
        """
        cursor.execute(query, (admin_id,))
        result = cursor.fetchone()

        if not result:
            return jsonify({"error": f"No settings found for Admin_id {admin_id}."}), 404

        # Prepare the response
        settings = {
            'key': result[0],
            'text_translation_endpoint': result[1],
            'document_translation_endpoint': result[2],
            'region': result[3],
            'storage_connection_string': result[4]
        }

        # Close the connection
        cursor.close()
        connection.close()

        return jsonify(settings), 200

    except Exception as e:
        logging.error(f"Error: {e}")
        return jsonify({"error": "An error occurred while retrieving the settings."}), 500
