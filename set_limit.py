from flask import Flask, request, jsonify
import psycopg2
import os  # Assuming you have logging_config.py
import datetime

app = Flask(__name__)
print("Starting modifier sequence update server")

# Database configuration
DB_CONFIG = {
    'dbname': os.getenv('DB_NAME'),
    'user': os.getenv('DB_USER'),
    'password': os.getenv('DB_PASSWORD'),
    'host': os.getenv('DB_HOST'),
    'port': os.getenv('DB_PORT')
}


def connect_db():
    """
    Establishes a connection to the PostgreSQL database.
    """
    try:
        connection = psycopg2.connect(**DB_CONFIG)
        print("Connected to database")
        return connection
    except psycopg2.Error as e:
        print(f"Error connecting to the database: {e}")
        print(f"Error connecting to the database: {e}")
        return None


@app.route('/update_token_limit', methods=['POST'])
def update_token_limit():
    """
    Endpoint to update the token limit in the database.
    Expects a JSON payload with a dictionary containing the 'token_limit' key.
    """
    data = request.get_json()

    if not data or not isinstance(data, dict) or 'token_limit' not in data:
        print("Invalid input.  Expecting a dictionary with a 'token_limit' key.")
        return jsonify({'error': "Invalid input.  Expecting a dictionary with a 'token_limit' key."}), 400

    token_limit = data['token_limit']

    connection = connect_db()
    if not connection:
        print("Failed to connect to the database")
        return jsonify({"error": "Failed to connect to the database."}), 500

    try:
        cursor = connection.cursor()

        # Update query to set the token_limit
        update_query = """
            UPDATE alta_var_settings
            SET value = %s
            WHERE key = 'token_limit';
            """
        cursor.execute(update_query, (token_limit,))  # Use %s for safety

        connection.commit()
        print("Token limit updated successfully.")
        return jsonify({'message': 'Token limit updated successfully.'}), 200

    except psycopg2.Error as e:
        connection.rollback()
        print(f"Database error: {e}")
        return jsonify({'error': f'Database error: {e}'}), 500

    finally:
        if cursor:
            cursor.close()
        if connection:
            connection.close()


if __name__ == '__main__':
    app.run(debug=True)  # remove debug=True for production
