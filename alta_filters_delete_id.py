# File: alta_filters_delete_id.py
import os
from flask import request, jsonify
import psycopg2
from psycopg2 import sql




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
# Database configuration
DB_CONFIG = {
    'dbname': os.getenv('DB_NAME'),  # 'settings_db' is the default if env variable is not set
    'user': os.getenv('DB_USER'),
    'password': os.getenv('DB_PASSWORD'),
    'host': os.getenv('DB_HOST'),
    'port': os.getenv('DB_PORT')
}
TABLE_NAME = "alta_filters"  # Hardcoded table name

def delete_row_by_id(row_id):
    connection = None
    try:
        # Connect to the PostgreSQL database
        connection = psycopg2.connect(
            dbname=DB_CONFIG['dbname'],
            user=DB_CONFIG['user'],
            password=DB_CONFIG['password'],
            host=DB_CONFIG['host'],
            port=DB_CONFIG['port']
        )
        cursor = connection.cursor()
        
        # Create the SQL delete query with hardcoded table name
        delete_query = sql.SQL("DELETE FROM {table} WHERE id = %s").format(
            table=sql.Identifier(TABLE_NAME)
        )
        
        # Execute the delete query
        cursor.execute(delete_query, (row_id,))
        
        # Commit the transaction
        connection.commit()
        
        # Check if the row was deleted
        if cursor.rowcount > 0:
            return True, f"Row with id {row_id} deleted successfully."
        else:
            return False, f"No row found with id {row_id}."
            
    except (Exception, psycopg2.Error) as error:
        return False, f"Error while connecting to PostgreSQL: {error}"
    
    finally:
        # Close the database connection
        if connection:
            cursor.close()
            connection.close()

# This function is designed to be imported and used in other Flask applications
def handle_delete_request():




    auth_error = validate_bearer_token(request, 'A7x!G2p@Q9#L')  # Replace 'A7x!G2p@Q9#L' with your actual token
    if auth_error:
        return auth_error
    


    # Get row_id from query parameter
    row_id = request.args.get('id')
    
    if not row_id:
        return jsonify({"status": "error", "message": "Missing required query parameter: id"}), 400
    
    try:
        # Convert id to integer
        row_id = int(row_id)
    except ValueError:
        return jsonify({"status": "error", "message": "Invalid id format. Must be an integer."}), 400
    
    success, message = delete_row_by_id(row_id)
    
    if success:
        return jsonify({"status": "success", "message": message}), 200
    else:
        return jsonify({"status": "error", "message": message}), 404 if "No row found" in message else 500


# For standalone testing - only runs if this file is executed directly
if __name__ == "__main__":
    from flask import Flask
    app = Flask(__name__)
    
    @app.route('/delete', methods=['DELETE'])
    def delete_row():
        return handle_delete_request()
    
    # Use environment variable for port if available, otherwise default to 5000
    port = int(os.environ.get("PORT", 5000))
    # In production, you would want to set debug=False
    app.run(host="0.0.0.0", port=port, debug=True)
