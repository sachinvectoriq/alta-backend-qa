from flask import Flask, jsonify, request
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

# Database connection details (Replace these with your actual values)
DB_CONFIG = {
    'dbname': os.getenv('DB_NAME'),  # 'settings_db' is the default if env variable is not set
    'user': os.getenv('DB_USER'),
    'password': os.getenv('DB_PASSWORD'),
    'host': os.getenv('DB_HOST'),
    'port': os.getenv('DB_PORT')
}


def get_db_connection():
    conn = psycopg2.connect(
        dbname=DB_CONFIG['dbname'],
        user=DB_CONFIG['user'],
        password=DB_CONFIG['password'],
        host=DB_CONFIG['host'],
        port=DB_CONFIG['port']
    )
    return conn

@app.route('/get_grouped_filters', methods=['GET'])
@app.route('/get_grouped_filters', methods=['GET'])
def get_grouped_filters():

    auth_error = validate_bearer_token(request, 'A7x!G2p@Q9#L')  # Replace with your actual token
    if auth_error:
        return auth_error

    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, modifier, value, system_prompt, user_prompt, sequence, status
            FROM alta_filters
        """)
        
        columns = [desc[0] for desc in cursor.description]
        data = [dict(zip(columns, row)) for row in cursor.fetchall()]
        
        # Grouping by modifier
        grouped_data = {}
        for item in data:
            modifier = item["modifier"]
            if modifier not in grouped_data:
                grouped_data[modifier] = {
                    "modifier": modifier,
                    "sequence": item["sequence"],
                    "status": item["status"],
                    "values": []
                }
            grouped_data[modifier]["values"].append({
                "id": item["id"],
                "modifier": item["modifier"],
                "value": item["value"],
                "system": item["system_prompt"],
                "user": item["user_prompt"]
            })

        cursor.close()
        conn.close()
        
        return jsonify(list(grouped_data.values()))
    
    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == '__main__':
    app.run(debug=True)
