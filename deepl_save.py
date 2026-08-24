from flask import request, jsonify
import psycopg2
import os
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

# Function to save DeepL settings
def save_settings_deepl():
    if 'admin_id' not in request.form or 'api_key' not in request.form:
        return jsonify({"error": "Missing admin_id or api_key"}), 400

    admin_id = request.form['admin_id']
    api_key = request.form['api_key']

    conn = get_db_connection()
    if not conn:
        return jsonify({"error": "Database connection failed"}), 500

    try:
        cursor = conn.cursor()
        query = """
        INSERT INTO deepl_settings (admin_id, api_key)
        VALUES (%s, %s)
        ON CONFLICT (admin_id) DO UPDATE
        SET api_key = EXCLUDED.api_key;
        """
        cursor.execute(query, (admin_id, api_key))
        conn.commit()
        cursor.close()
        conn.close()
        return jsonify({"message": "Settings saved successfully!"}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500
