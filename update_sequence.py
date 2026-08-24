from flask import Flask, request, jsonify
import psycopg2
import os # Assuming you have logging_config.py

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

@app.route('/update_modifier_sequence', methods=['POST'])
def update_modifier_sequence():
    """
    Endpoint to update the sequence of modifiers.
    Expects a JSON payload with a list of dictionaries, where each dictionary
    contains 'name' and 'sequence' keys.
    """
    data = request.get_json()

    if not data or not isinstance(data, list):
        print("Invalid input. Expecting a list of dictionaries.")
        return jsonify({'error': 'Invalid input. Expecting a list of dictionaries.'}), 400

    connection = connect_db()
    if not connection:
        print("Failed to connect to the database")
        return jsonify({"error": "Failed to connect to the database."}), 500

    try:
        cursor = connection.cursor()

        for item in data:
            if 'name' not in item or 'sequence' not in item:
                print("Each item must have 'name' and 'sequence' fields.")
                return jsonify({'error': 'Each item must have "name" and "sequence" fields.'}), 400

            name = item['name']
            sequence = item['sequence']

            # Update query to set the sequence for a modifier
            update_query = """
            UPDATE alta_filters
            SET sequence = %s
            WHERE modifier = %s;
            """
            cursor.execute(update_query, (sequence, name))

        connection.commit()
        print("Modifier sequences updated successfully.")
        return jsonify({'message': 'Modifier sequences updated successfully.'}), 200

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