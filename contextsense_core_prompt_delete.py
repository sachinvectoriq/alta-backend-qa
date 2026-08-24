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




# Database connection parameters
DB_CONFIG = {
    'dbname': os.getenv('DB_NAME'),  # 'settings_db' is the default if env variable is not set
    'user': os.getenv('DB_USER'),
    'password': os.getenv('DB_PASSWORD'),
    'host': os.getenv('DB_HOST'),
    'port': os.getenv('DB_PORT')
}

def get_db_connection():
    """Create and return a database connection"""
    conn = psycopg2.connect(
        dbname=DB_CONFIG['dbname'],
        user=DB_CONFIG['user'],
        password=DB_CONFIG['password'],
        host=DB_CONFIG['host'],
        port=DB_CONFIG['port']
    )
    return conn

@app.route('/delete_core_prompt', methods=['DELETE'])
def delete_core_prompt():


    auth_error = validate_bearer_token(request, 'A7x!G2p@Q9#L')  # Replace with actual token
    if auth_error:
        return auth_error
    
    
    try:
        # Get core_prompt_id from query parameters
        core_prompt_id = request.args.get('core_prompt_id')
        if not core_prompt_id:
            return jsonify({"error": "Missing required parameter: core_prompt_id"}), 400

        # Connect to the database
        conn = get_db_connection()
        cursor = conn.cursor()

        # Execute the DELETE query
        cursor.execute("DELETE FROM contextsense_core_prompt WHERE core_prompt_id = %s RETURNING core_prompt_id;", (core_prompt_id,))
        
        # Fetch the deleted row ID
        deleted_row = cursor.fetchone()
        
        # If no rows were deleted, return a 404 response
        if not deleted_row:
            conn.rollback()
            cursor.close()
            conn.close()
            return jsonify({"error": f"No entry found with core_prompt_id {core_prompt_id}"}), 404

        # Commit the transaction
        conn.commit()
        cursor.close()
        conn.close()

        return jsonify({
            "message": f"Deleted core_prompt_id {deleted_row[0]} successfully"
        }), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == '__main__':
    app.run(debug=True)
