from flask import Flask, request, jsonify
import psycopg2
from datetime import datetime
import os

app = Flask(__name__)

# Default Hardcoded system and user prompts
DEFAULT_SYSTEM_PROMPT = "The following portion of the prompt may have contradictory statements which require you to have the context which best matches the majority of the statements: You are communicating with someone in a country which speaks {target_language}."
DEFAULT_USER_PROMPT = (
    "The {modifier_value} of what you are preparing is {user_defined}. "
    "The edits should take into account the {user_defined} context in {target_language} using wording and jargon appropriate to the context, "
    "however, the meaning of the text in {source_language} needs to remain."
)

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


def insert_into_alta_filters(modifier, value, system_prompt, user_prompt, created_by, sequence, status):
    connection = None
    DB_CONFIG = {
        'dbname': os.getenv('DB_NAME'),
        'user': os.getenv('DB_USER'),
        'password': os.getenv('DB_PASSWORD'),
        'host': os.getenv('DB_HOST'),
        'port': os.getenv('DB_PORT')
    }
    try:
        connection = psycopg2.connect(**DB_CONFIG)
        cursor = connection.cursor()

        # Determine next sequence if not provided
        if sequence is None:
            cursor.execute("SELECT MAX(sequence) FROM alta_filters")
            max_sequence = cursor.fetchone()[0]
            sequence = (max_sequence or 0) + 1
        else:
            sequence = int(sequence)

        current_time = datetime.now()

        insert_query = """
        INSERT INTO alta_filters (
            modifier, value, system_prompt, user_prompt,
            created_by, created_at, updated_at, sequence, status
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING id, modifier, value, system_prompt, user_prompt, sequence, status
        """

        record_to_insert = (
            modifier, value, system_prompt, user_prompt,
            created_by, current_time, current_time, sequence, status
        )

        cursor.execute(insert_query, record_to_insert)
        new_id, modifier, value, system_prompt, user_prompt, sequence, status = cursor.fetchone()
        connection.commit()

        return True, {
            "id": new_id,
            "modifier": modifier,
            "value": value,
            "system": system_prompt,
            "user": user_prompt,
            "sequence": sequence,
            "status": status
        }, "Record inserted successfully"

    except (Exception, psycopg2.Error) as error:
        if connection:
            connection.rollback()
        return False, None, f"Database error: {error}"
    finally:
        if connection:
            cursor.close()
            connection.close()



@app.route('/api/alta_filters', methods=['POST'])
def add_alta_filter():
    # Validate Bearer token
    auth_error = validate_bearer_token(request, 'A7x!G2p@Q9#L')  # Replace with actual token
    if auth_error:
        return auth_error

    # Extract query parameters
    modifier = request.args.get('modifier')  # Required
    value = request.args.get('value', 'User defined')
    created_by = request.args.get('created_by')
    sequence = request.args.get('sequence', None)
    status = request.args.get('status', 'active')

    system_prompt = request.args.get('system_prompt', DEFAULT_SYSTEM_PROMPT)
    user_prompt = request.args.get('user_prompt', DEFAULT_USER_PROMPT)

    if not modifier:
        return jsonify({"success": False, "error": "Missing required field: 'modifier' is mandatory."}), 400

    if user_prompt == DEFAULT_USER_PROMPT:
        user_prompt = user_prompt.replace("{modifier_value}", modifier)

    # Insert data into database
    success, record, message = insert_into_alta_filters(
        modifier, value, system_prompt, user_prompt, created_by, sequence, status
    )

    if success:
        response = {
            "data": record,
            "message": message,
            "success": True
        }
        return jsonify(response), 201
    else:
        return jsonify({
            "success": False,
            "error": message
        }), 500


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
