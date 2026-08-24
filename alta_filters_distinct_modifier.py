import psycopg2
import os
from flask import Flask, request, jsonify




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



def get_distinct_modifiers():



    auth_error = validate_bearer_token(request, 'A7x!G2p@Q9#L')  # Replace 'A7x!G2p@Q9#L' with your actual token
    if auth_error:
        return auth_error


    DB_CONFIG = {
    'dbname': os.getenv('DB_NAME'),  # 'settings_db' is the default if env variable is not set
    'user': os.getenv('DB_USER'),
    'password': os.getenv('DB_PASSWORD'),
    'host': os.getenv('DB_HOST'),
    'port': os.getenv('DB_PORT')
    }
    
    try:
        # Establish connection
        conn = psycopg2.connect(
        dbname=DB_CONFIG['dbname'],
        user=DB_CONFIG['user'],
        password=DB_CONFIG['password'],
        host=DB_CONFIG['host'],
        port=DB_CONFIG['port']
    )
        
        # Create cursor
        cur = conn.cursor()
        
        # Execute query
        cur.execute("SELECT DISTINCT modifier FROM alta_filters;")
        
        # Fetch results
        modifiers = [row[0] for row in cur.fetchall()]
        
        # Close cursor and connection
        cur.close()
        conn.close()
        
        return modifiers
    
    except Exception as e:
        print(f"Error: {e}")
        return None


