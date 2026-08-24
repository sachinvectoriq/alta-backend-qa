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

@app.route('/log_document_translation', methods=['POST'])
def log_document_translation():
    """
    Endpoint to log user document translation details.
    Expects form data: 'user', 'document_name', 'source_language', 'target_language', 
                         'billed_characters', 'size_of_the_document', 'vendor'.
    """
    # Get the values from form data
    user = request.form.get('user')
    document_name = request.form.get('document_name')
    source_language = request.form.get('source_language')
    target_language = request.form.get('target_language')
    billed_characters = request.form.get('billed_characters')
    size_of_the_document = request.form.get('size_of_the_document')
    vendor = request.form.get('vendor')
    domain_name = request.form.get('domain_name',False)
    login_session_id = request.form.get('login_session_id')

    # Check for required fields
    if not user or not document_name or not source_language or not target_language or not vendor or not login_session_id:
        return jsonify({"error": "The 'user', 'document_name', 'source_language', 'target_language', 'vendor', and 'login_session_id' fields are required."}), 400

    # Convert billed_characters and size_of_the_document to integers, or None if not provided
    try:
        billed_characters = int(billed_characters) if billed_characters else None
        size_of_the_document = int(size_of_the_document) if size_of_the_document else None
        login_session_id = int(login_session_id) if login_session_id else None
    except ValueError:
        return jsonify({"error": "billed_characters, size_of_the_document, and login_session_id must be integers."}), 400

    # Convert current UTC time to Eastern Standard Time (EST)
    utc_now = datetime.utcnow()
    eastern = pytz.timezone('America/New_York')
    eastern_time = pytz.utc.localize(utc_now).astimezone(eastern)
    # Get current UTC time
    # utc_now = datetime.utcnow()

    connection = connect_db()
    if not connection:
        return jsonify({"error": "Failed to connect to the database."}), 500

    try:
        cursor = connection.cursor()
        if domain_name:
            insert_query = """
            INSERT INTO user_docu_trans_log 
            ("user", "document_name", "source_language", "target_language", 
             "billed_characters", "size_of_the_document", "vendor", "date_and_time","domain_name", "login_session_id")
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s);
            """
            cursor.execute(insert_query, (user, document_name, source_language, target_language, 
                                          billed_characters, size_of_the_document, vendor, eastern_time, domain_name, login_session_id))
            connection.commit()
        else:
            insert_query = """
            INSERT INTO user_docu_trans_log 
            ("user", "document_name", "source_language", "target_language", 
             "billed_characters", "size_of_the_document", "vendor", "date_and_time", "login_session_id")
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s);
            """
            cursor.execute(insert_query, (user, document_name, source_language, target_language, 
                                          billed_characters, size_of_the_document, vendor, eastern_time, login_session_id))
            connection.commit()
            

        return jsonify({"message": "Document translation details logged successfully."}), 201

    except psycopg2.Error as e:
        return jsonify({"error": f"Database error: {e}"}), 500

    finally:
        cursor.close()
        connection.close()

if __name__ == '__main__':
    app.run(debug=True)
