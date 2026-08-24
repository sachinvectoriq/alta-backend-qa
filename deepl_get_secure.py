from flask import Flask, request, jsonify
import psycopg2
import os

app = Flask(__name__)

# Database connection details


DB_CONFIG = {
    'dbname': os.getenv('DB_NAME'),  # 'settings_db' is the default if env variable is not set
    'user': os.getenv('DB_USER'),
    'password': os.getenv('DB_PASSWORD'),
    'host': os.getenv('DB_HOST'),
    'port': os.getenv('DB_PORT')
}


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



# Function to connect to the database
def get_db_connection():
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        return conn
    except Exception as e:
        print(f"Error connecting to the database: {e}")
        return None

# Function to retrieve settings for DeepL

def get_settings_deepl_secure():
    # Check if 'admin_id' is provided in the form data
    auth_error = validate_bearer_token(request, 'A7x!G2p@Q9#L')  # Replace 'A7x!G2p@Q9#L' with your actual token
    if auth_error:
        return auth_error
    admin_id = request.form.get('admin_id')
    if not admin_id:
        return jsonify({"error": "Missing admin_id"}), 400

    # Establish a connection to the database
    conn = get_db_connection()
    if not conn:
        return jsonify({"error": "Database connection failed"}), 500

    try:
        cursor = conn.cursor()
        # SQL query to retrieve the api_key for the given admin_id
        query = "SELECT api_key FROM deepl_settings WHERE admin_id = %s;"
        cursor.execute(query, (admin_id,))
        
        result = cursor.fetchone()
        cursor.close()
        conn.close()

        # Check if a result was found
        if result:
            return jsonify({"admin_id": admin_id, "api_key": result[0]}), 200
        else:
            return jsonify({"error": "No settings found for the given admin_id"}), 404

    except Exception as e:
        return jsonify({"error": str(e)}), 500
