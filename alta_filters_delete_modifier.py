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

@app.route('/delete_filter', methods=['DELETE'])
def delete_modifier():


    auth_error = validate_bearer_token(request, 'A7x!G2p@Q9#L')  # Replace 'A7x!G2p@Q9#L' with your actual token
    if auth_error:
        return auth_error
    

    try:
        # Get the modifier from query parameters
        modifier = request.args.get('modifier')
        if not modifier:
            return jsonify({"error": "Missing required parameter: modifier"}), 400

        # Connect to the database
        conn = get_db_connection()
        cursor = conn.cursor()

        # Execute the DELETE query
        cursor.execute("DELETE FROM alta_filters WHERE modifier = %s RETURNING id;", (modifier,))
        
        # Fetch IDs of deleted rows
        deleted_rows = cursor.fetchall()
        rows_affected = len(deleted_rows)

        # If no rows were deleted, return a 404 response
        if rows_affected == 0:
            conn.rollback()
            cursor.close()
            conn.close()
            return jsonify({"error": f"No filters found with modifier '{modifier}'"}), 404

        # Commit the transaction
        conn.commit()
        cursor.close()
        conn.close()

        return jsonify({
            "message": f"Deleted {rows_affected} filters with modifier '{modifier}'",
            "deleted_ids": [row[0] for row in deleted_rows]
        }), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == '__main__':
    app.run(debug=True)
