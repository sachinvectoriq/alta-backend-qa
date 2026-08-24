from flask import jsonify
import psycopg2
from psycopg2 import sql
from db_connection import connect_db  # Import the connection function from a shared module
from logging_config import log, flush  # Import log and flush
import traceback  # Import the traceback module


def store_feedback(feedback_data):
    log('INFO', "Attempting to store feedback data in the database.",
        data={'feedback_keys': list(feedback_data.keys())})
    """Store user feedback in the database."""
    user_name = feedback_data.get('user_name')
    feedback_text = feedback_data.get('feedback_text')
    source_language = feedback_data.get('source_language')
    target_language = feedback_data.get('target_language')
    document_name = feedback_data.get('document_name')
    source_text = feedback_data.get('source_text')
    translated_text = feedback_data.get('translated_text')
    vendor = feedback_data.get('vendor')
    glossary_filename = feedback_data.get('glossary_filename')
    domain_name=feedback_data.get('domain_name',False)
    #session_id = feedback_data.get('session_id')

    conn = None
    cursor = None
    try:
        log('INFO', 'Connecting to the database for feedback storage.')
        conn = connect_db()  # Use the connection function from your db module
        if not conn:
            log('ERROR', 'Failed to obtain a database connection for feedback storage.')
            flush()
            return jsonify({"error": "Failed to connect to the database."}), 500

        cursor = conn.cursor()

        insert_query = sql.SQL("""
            INSERT INTO user_feedback (
                user_name, feedback_text, source_language, 
                target_language, document_name, 
                source_text, translated_text, vendor ,glossary_filename,domain_name
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """)

        # Log the intent to execute the query, perhaps with sanitized data
        log('INFO', "Executing insert query for user feedback.",
            data={'user_name': user_name, 'document_name': document_name, 'vendor': vendor})

        cursor.execute(insert_query, (user_name, feedback_text, source_language,
                                      target_language, document_name,
                                      source_text, translated_text, vendor, glossary_filename,domain_name))
        conn.commit()
        log('INFO', "Feedback stored into database successfully.", user_name=user_name)
        flush()  # Flush logs after successful operation
        return jsonify({"message": "Feedback added successfully"}), 201

    except psycopg2.Error as db_error:
        if conn:
            conn.rollback()
            log('WARNING', "Database transaction rolled back for feedback storage due to error.")

        # Capture and include traceback for database errors
        error_traceback = traceback.format_exc()
        log('ERROR',
            f"Database error storing feedback: {db_error}",
            data={'user_name': user_name, 'document_name': document_name, 'traceback': error_traceback})
        flush()  # Flush logs on database error
        return jsonify({"error": f"Database error: {str(db_error)}"}), 500
    except Exception as e:
        # Capture and include traceback for any unexpected errors
        error_traceback = traceback.format_exc()
        log('CRITICAL',
            f"An unexpected error occurred while storing feedback: {e}",
            data={'user_name': user_name, 'document_name': document_name, 'traceback': error_traceback})
        flush()  # Flush logs on any critical unexpected error
        return jsonify({"error": str(e)}), 500

    finally:
        if cursor:
            cursor.close()
            log('INFO', 'Database cursor closed for feedback storage.')
        if conn:
            conn.close()
            log('INFO', 'Database connection closed for feedback storage.')
        # Ensure final flush, especially important for functions not directly triggered by HTTP request end
        flush()
