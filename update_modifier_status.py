from flask import Flask, request, jsonify
import psycopg2
import os

app = Flask(__name__)
print("Starting modifier status update server")

# Database configuration
DB_CONFIG = {
    'dbname': os.getenv('DB_NAME'),
    'user': os.getenv('DB_USER'),
    'password': os.getenv('DB_PASSWORD'),
    'host': os.getenv('DB_HOST'),
    'port': os.getenv('DB_PORT')
}

def connect_db():
    """Establishes a connection to the PostgreSQL database."""
    try:
        connection = psycopg2.connect(**DB_CONFIG)
        print("Connected to PostgreSQL database")
        return connection
    except psycopg2.Error as e:
        print(f"Error connecting to the database: {e}")
        return None

@app.route('/update_modifier_status', methods=['POST'])
def update_modifier_status():
    """
    Endpoint to update the status of a single modifier.
    Expects a JSON payload with 'modifier' and 'status' keys.
    """
    data = request.get_json()

    if not data or not isinstance(data, dict):
        print("Invalid input. Expecting a single dictionary.")
        return jsonify({'error': 'Invalid input. Expecting a single dictionary.'}), 400

    if 'modifier' not in data or 'status' not in data:
        print("Missing 'modifier' or 'status' in JSON payload.")
        return jsonify({'error': 'Missing "modifier" or "status" fields.'}), 400

    modifier_name = data['modifier']
    new_status = data['status']

    connection = connect_db()
    if not connection:
        print("Failed to connect to the database")
        return jsonify({"error": "Failed to connect to the database."}), 500

    try:
        cursor = connection.cursor()

        # Update query to set the status for the specified modifier
        update_query = """
            UPDATE alta_filters
            SET status = %s
            WHERE modifier = %s;
        """
        cursor.execute(update_query, (new_status, modifier_name))

        connection.commit()
        print(f"Modifier '{modifier_name}' status updated to '{new_status}'.")
        return jsonify({'message': f"Modifier '{modifier_name}' status updated to '{new_status}'."}), 200

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
    app.run(debug=True) #remove debug=True for production