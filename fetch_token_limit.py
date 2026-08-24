from flask import Flask, jsonify
import psycopg2
import os

app = Flask(__name__)

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
    Establishes a connection to PostgreSQL safely.
    """
    try:
        connection = psycopg2.connect(**DB_CONFIG)

        # Optional but SAFE way to set timeout (NOT in connect args)
        cursor = connection.cursor()
        cursor.execute("SET statement_timeout = 5000")  # 5 sec query timeout
        cursor.close()

        print("Connected to database")
        return connection

    except psycopg2.Error as e:
        print(f"Error connecting to the database: {e}")
        return None


@app.route('/get_token_limit', methods=['GET'])
def get_token_limit():
    connection = None
    cursor = None

    try:
        connection = connect_db()

        if not connection:
            return jsonify({
                "error": "Failed to connect to database"
            }), 500

        cursor = connection.cursor()

        query = """
            SELECT value
            FROM alta_var_settings
            WHERE key = 'token_limit';
        """

        cursor.execute(query)
        result = cursor.fetchone()

        if not result:
            return jsonify({
                "error": "token_limit not found in database"
            }), 404

        token_limit_str = result[0]

        try:
            token_limit = int(token_limit_str)
        except ValueError:
            return jsonify({
                "error": "token_limit is not a valid integer",
                "raw_value": token_limit_str
            }), 500

        return jsonify({
            "token_limit": token_limit
        }), 200

    except psycopg2.Error as e:
        return jsonify({
            "error": f"Database error: {str(e)}"
        }), 500

    except Exception as e:
        return jsonify({
            "error": f"Unexpected error: {str(e)}"
        }), 500

    finally:
        if cursor:
            cursor.close()
        if connection:
            connection.close()


if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
