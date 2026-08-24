from flask import Flask, request, jsonify
import psycopg2
import pytz
from datetime import datetime
import os

app = Flask(__name__)

# Database configuration
DB_CONFIG = {
    'dbname': os.getenv('DB_NAME'),  # 'settings_db' is the default if env variable is not set
    'user': os.getenv('DB_USER'),
    'password': os.getenv('DB_PASSWORD'),
    'host': os.getenv('DB_HOST'),
    'port': os.getenv('DB_PORT')
}

def connect_db():
    """
    Establishes a connection to the database.
    """
    try:
        connection = psycopg2.connect(**DB_CONFIG)
        return connection
    except psycopg2.Error as e:
        print(f"Error connecting to the database: {e}")
        return None

@app.route('/log_text_translation', methods=['POST'])
def log_text_translation():
    """
    Endpoint to log user text translation details.
    Expects form data input: 
    'user', 'source_text', 'translated_text', 'source_language', 'target_language', 'billed_characters', 'vendor'
    """
    # Get the values from form data
    user = request.form.get('user')
    source_text = request.form.get('source_text')
    translated_text = request.form.get('translated_text')
    source_language = request.form.get('source_language')
    target_language = request.form.get('target_language')
    billed_characters = request.form.get('billed_characters')
    vendor = request.form.get('vendor')
    domain_name = request.form.get('domain_name',False)
    
    # Properly convert refinement_used to boolean
    refinement_used_str = request.form.get('refinement_used', 'false').lower()
    refinement_used = refinement_used_str in ('true', 'yes', '1', 't', 'y')
    
    login_session_id = request.form.get('login_session_id')

    # Check for required values
    if not user or not source_text or not translated_text:
        return jsonify({"error": "The 'user', 'source_text', and 'translated_text' fields are required."}), 400

    # Convert current UTC time to Eastern Standard Time (EST)
    utc_now = datetime.utcnow()
    eastern = pytz.timezone('America/New_York')
    eastern_time = pytz.utc.localize(utc_now).astimezone(eastern)

    connection = connect_db()
    if not connection:
        return jsonify({"error": "Failed to connect to the database."}), 500

    try:
        cursor = connection.cursor()
        if domain_name:
            insert_query = """
            INSERT INTO user_text_trans_log 
            ("user", "source_text", "translated_text", "source_language", "target_language", 
             "billed_characters", "vendor", "date_and_time", "refinement_used", "login_session_id", "domain_name")
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING log_id, login_session_id;
            """
            cursor.execute(insert_query, (user, source_text, translated_text, source_language, target_language, 
                                          billed_characters, vendor, eastern_time, refinement_used, login_session_id, domain_name))
            # Fetch the generated log_id
            log_id, login_session_id = cursor.fetchone()
            connection.commit()
        
        else:
            # Insert query to log text translation details
            insert_query = """
            INSERT INTO user_text_trans_log 
            ("user", "source_text", "translated_text", "source_language", "target_language", 
             "billed_characters", "vendor", "date_and_time", "refinement_used", "login_session_id")
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING log_id, login_session_id;
            """
            cursor.execute(insert_query, (user, source_text, translated_text, source_language, target_language, 
                                          billed_characters, vendor, eastern_time, refinement_used, login_session_id))
            # Fetch the generated log_id
            log_id, login_session_id = cursor.fetchone()
            connection.commit()

        return jsonify({"message": "Text translation details logged successfully.",
                        "log_id": log_id,
                        "login_session_id": login_session_id}), 201

    except psycopg2.Error as e:
        return jsonify({"error": f"Database error: {e}"}), 500

    finally:
        if connection:
            cursor.close()
            connection.close()

if __name__ == '__main__':
    app.run(debug=True)
