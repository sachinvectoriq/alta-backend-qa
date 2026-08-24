from flask import Flask, request, jsonify
import psycopg2
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



# Database connection
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

@app.route('/add_prompt', methods=['GET'])
def add_prompt():
    auth_error = validate_bearer_token(request, 'A7x!G2p@Q9#L')  # Replace with actual token
    if auth_error:
        return auth_error

    prompt = request.args.get('prompt')
    created_by = request.args.get('created_by', None)  # Optional

    if not prompt:
        return jsonify({"error": "prompt is required"}), 400

    try:
        conn = get_db_connection()
        cur = conn.cursor()

        # Insert data into table
        cur.execute("""
            INSERT INTO contextsense_core_prompt (prompt, created_by) 
            VALUES (%s, %s)
        """, (prompt, created_by))

        conn.commit()
        cur.close()
        conn.close()

        return jsonify({"message": "Prompt added successfully"}), 201

    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True)
