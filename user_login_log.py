from flask import Flask, request, jsonify
import psycopg2
import os

app = Flask(__name__)

# Database configuration
DB_CONFIG = {
    'dbname': os.getenv('DB_NAME'),  # 'settings_db' is the default if env variable is not set
    'user': os.getenv('DB_USER'),
    'password': os.getenv('DB_PASSWORD'),
    'host': os.getenv('DB_HOST'),
    'port': os.getenv('DB_PORT')
}

def connect_db():
    """
    Establishes a connection to the database.
    """
    try:
        connection = psycopg2.connect(**DB_CONFIG)
        return connection
    except psycopg2.Error as e:
        print(f"Error connecting to the database: {e}")
        return None

@app.route('/log_user_login', methods=['POST'])
def log_user_login():
    """
    Endpoint to log user login details.
    Expects form data input: {"user": "username"}
    """
    user = request.form.get('user')  # Fetch 'user' from form data
    domain_name=request.form.get('domain_name',False)

    if not user:
        return jsonify({"error": "The 'user' field is required."}), 400

    connection = connect_db()
    if not connection:
        return jsonify({"error": "Failed to connect to the database."}), 500

    try:
        cursor = connection.cursor()
        # Use double quotes for the "user" column to avoid conflicts with the reserved keyword
        if domain_name:
            insert_query = """
            INSERT INTO user_login_log ("user","domain_name")
            VALUES (%s,%s)
            RETURNING login_session_id;
            """
            cursor.execute(insert_query, (user,domain_name,))
        else:
            insert_query = """
            INSERT INTO user_login_log ("user")
            VALUES (%s)
            RETURNING login_session_id;
            """
            cursor.execute(insert_query, (user,))
        login_session_id = cursor.fetchone()[0]
        connection.commit()
        return jsonify({"message": "Login details added successfully.",
                        "login_session_id": login_session_id}), 201
    except psycopg2.Error as e:
        return jsonify({"error": f"Database error: {e}"}), 500
    finally:
        cursor.close()
        connection.close()

if __name__ == '__main__':
    app.run(debug=True)
