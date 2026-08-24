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



# Function to connect to the database
def get_db_connection():
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        return conn
    except Exception as e:
        print(f"Error connecting to the database: {e}")
        return None

# Function to retrieve settings for DeepL

def get_settings_deepl():
    # Check if 'admin_id' is provided in the form data
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
