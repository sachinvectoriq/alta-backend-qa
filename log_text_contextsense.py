from flask import Flask, request, jsonify
import psycopg2
import os
#from logging_config import logger  # Assuming you have this
from typing import List, Dict

app = Flask(__name__)
#logger.info("Starting context sense log server")

# Database configuration (use environment variables)
DB_CONFIG = {
    'dbname': os.getenv('DB_NAME'),  # 'settings_db' is the default if env variable is not set
    'user': os.getenv('DB_USER'),
    'password': os.getenv('DB_PASSWORD'),
    'host': os.getenv('DB_HOST'),
    'port': os.getenv('DB_PORT')
}

def connect_db():
    """Establishes a connection to the database."""
    try:
        connection = psycopg2.connect(**DB_CONFIG)
#        logger.info("Connecting to database")
        return connection
    except psycopg2.Error as e:
#        logger.error(f"Error connecting to the database: {e}")
        print(f"Error connecting to the database: {e}")  # Keep for debugging
        return None

def insert_context_selection(cursor, login_session_id, modifier_type, modifier_value, system_prompt, user_prompt, refined_text, explanation,domain_name):
    """
    Inserts a single context selection into the ContextSelections table.
    """
    insert_query = """
        INSERT INTO contextsense (
            login_session_id, modifier_type, modifier_value, system_prompt, user_prompt, refined_text, explanation, domain_name
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s);
        """
    try:
        cursor.execute(
            insert_query,
            (login_session_id, modifier_type, modifier_value, system_prompt, user_prompt, refined_text, explanation, domain_name)
        )
        print("insert query executed")
    except psycopg2.Error as e:
 #       logger.error(f"Error inserting into ContextSelections: {e}")
        raise  # Re-raise to be caught in log_context_sense_data


@app.route('/log_contextsense', methods=['POST'])
def log_contextsense():
    """
    Endpoint to log context sense data and update the audit_log table.
    Expects JSON data with 'login_session_id', 'modifier_types', 'modifier_values',
    'system_prompts', 'user_prompts', 'refined_text', and 'explanation'.
    """
    try:
        data = request.get_json()
        login_session_id = data.get('login_session_id')
        modifier_types = data.get('modifier_types')
        modifier_values = data.get('modifier_values')
        system_prompts = data.get('system_prompts')
        user_prompts = data.get('user_prompts')
        refined_text = data.get('refined_text')
        explanation = data.get('explanation')
        domain_name = data.get('domain_name',False),
        log_id = data.get('log_id')
        print(data)

        if not all([login_session_id, modifier_types, modifier_values, system_prompts, user_prompts, refined_text, explanation]):
  #          logger.error("Missing required data")
            return jsonify({"error": "Missing required data in the JSON payload."}), 400

        if not (isinstance(modifier_types, list) and isinstance(modifier_values, list)) :
   #         logger.error("modifier fields are not lists")
            return jsonify({"error": "modifier_types, modifier_values, system_prompts, and user_prompts must be lists."}), 400

        if not (len(modifier_types) == len(modifier_values) ):
    #         logger.error("modifier lists are not of same length")
             return jsonify({"error": "modifier_types, modifier_values, system_prompts, and user_prompts must have the same number of elements."}), 400
        connection = connect_db()
        if not connection:
            return jsonify({"error": "Failed to connect to the database."}), 500

        cursor = connection.cursor()

        insert_context_selection(cursor, login_session_id, str(modifier_types), str(modifier_values), system_prompts, user_prompts, refined_text, explanation,domain_name)

        # Update refinement_used in audit_log
        update_query = """
            UPDATE user_text_trans_log
            SET refinement_used = true
            WHERE log_id = %s;
        """
        cursor.execute(update_query,(log_id,))
        print("Updated user text_trans_log")
        connection.commit()

     #   logger.info(f"Context sense data logged for login_session_id: {login_session_id}")
        return jsonify({"message": "Context sense data logged successfully."}), 200

    except psycopg2.Error as e:
        connection.rollback()
      #  logger.error(f"Database error: {e}")
        return jsonify({"error": f"Database error: {e}"}), 500
    except Exception as e:
       # logger.error(f"Error processing request: {e}")
        return jsonify({"error": f"Error processing request: {e}"}), 500
    finally:
        if connection:
            cursor.close()
            connection.close()
    return("database entry is suceesfully")

if __name__ == '__main__':
    app.run(debug=True)
