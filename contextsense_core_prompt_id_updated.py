from flask import Flask, request, jsonify
import psycopg2
from psycopg2.extras import RealDictCursor
import os

app = Flask(__name__)



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


# Database connection details
DB_CONFIG = {
    'dbname': os.getenv('DB_NAME'),  # 'settings_db' is the default if env variable is not set
    'user': os.getenv('DB_USER'),
    'password': os.getenv('DB_PASSWORD'),
    'host': os.getenv('DB_HOST'),
    'port': os.getenv('DB_PORT')
}

def get_db_connection():
    return psycopg2.connect(
        dbname=DB_CONFIG['dbname'],
        user=DB_CONFIG['user'],
        password=DB_CONFIG['password'],
        host=DB_CONFIG['host'],
        port=DB_CONFIG['port']
    )

@app.route('/update_prompt', methods=['PUT'])
def update_prompt():

    auth_error = validate_bearer_token(request, 'A7x!G2p@Q9#L')  # Replace with actual token
    if auth_error:
        return auth_error
    
    
    core_prompt_id = request.args.get('core_prompt_id')
    prompt = request.args.get('prompt')
    
    if not core_prompt_id or not prompt:
        return jsonify({"error": "Missing core_prompt_id or prompt parameter"}), 400
    
    try:
        core_prompt_id = int(core_prompt_id)  # Ensure it's an integer
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Update query
        cur.execute(
            """
            UPDATE contextsense_core_prompt
            SET prompt = %s
            WHERE core_prompt_id = %s
            RETURNING core_prompt_id, prompt;
            """,
            (prompt, core_prompt_id)
        )
        updated_row = cur.fetchone()
        conn.commit()
        cur.close()
        conn.close()
        
        if updated_row:
            return jsonify({"message": "Prompt updated successfully", "data": {"core_prompt_id": updated_row[0], "prompt": updated_row[1]}}), 200
        else:
            return jsonify({"error": "core_prompt_id not found"}), 404
        
    except ValueError:
        return jsonify({"error": "Invalid core_prompt_id. It must be an integer."}), 400
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True)
