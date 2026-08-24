import psycopg2
import os
import logging
from flask import Flask, request, jsonify

app = Flask(__name__)

@app.route('/save_settings', methods=['POST'])
def save_settings():
    try:
        # Parse input parameters from the request
        admin_id = "1"
        key = request.form.get('key')
        text_translation_endpoint = request.form.get('text_translation_endpoint')
        document_translation_endpoint = request.form.get('document_translation_endpoint')
        region = request.form.get('region')
        storage_connection_string = request.form.get('storage_connection_string')
        
        # Check for missing parameters
        if not (key and text_translation_endpoint and document_translation_endpoint and region and storage_connection_string):
            return jsonify({"error": "Missing one or more required parameters."}), 400
        
        # Get database connection details from environment variables
        host = os.getenv('DB_HOST')
        database = os.getenv('DB_NAME')
        user = os.getenv('DB_USER')
        password = os.getenv('DB_PASSWORD')
        port_str = os.getenv('DB_PORT')

        # Ensure all environment variables are set
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
        
        # Insert or update the data in the settings table
        insert_query = """
        INSERT INTO settings (admin_id, key, text_translation_endpoint, document_translation_endpoint, region, storage_connection_string)
        VALUES (%s, %s, %s, %s, %s, %s)
        ON CONFLICT (admin_id)
        DO UPDATE SET
            key = EXCLUDED.key,
            text_translation_endpoint = EXCLUDED.text_translation_endpoint,
            document_translation_endpoint = EXCLUDED.document_translation_endpoint,
            region = EXCLUDED.region,
            storage_connection_string = EXCLUDED.storage_connection_string;
        """
        
        cursor.execute(insert_query, (admin_id, key, text_translation_endpoint, document_translation_endpoint, region, storage_connection_string))
        
        # Commit the transaction
        connection.commit()
        
        # Close the connection
        cursor.close()
        connection.close()
        
        return jsonify({"message": f"Settings for Admin_id {admin_id} saved successfully."}), 200
    
    except psycopg2.Error as db_error:
        logging.error(f"Database error occurred: {db_error}", exc_info=True)
        return jsonify({"error": "A database error occurred while saving the settings."}), 500
    except Exception as e:
        logging.error(f"Error occurred: {e}", exc_info=True)
        return jsonify({"error": "An unexpected error occurred while saving the settings."}), 500

if __name__ == '__main__':
    app.run(debug=True)
