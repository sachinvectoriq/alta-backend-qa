from flask import Flask, request, jsonify
import psycopg2
import os
import datetime

# Import log and flush from your logging_config
#from logging_config import log, flush

app = Flask(__name__)
#log('INFO', "Starting database API server for alta_reports_access table.")

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
        #log('INFO', "Attempting to connect to the PostgreSQL database.")
        connection = psycopg2.connect(**DB_CONFIG)
        #log('INFO', "Successfully connected to database.")
        return connection
    except psycopg2.Error as e:
        #log('ERROR', f"Error connecting to the database: {e}", data={'db_config': {k: v for k, v in DB_CONFIG.items() if k != 'password'}})
        #flush()
        return None
    except Exception as e:
        #log('CRITICAL', f"An unexpected error occurred during database connection: {e}")
        #flush()
        return None


def insert_access_record(name, email, granted_by):
    """
    Function to insert a new record into alta_reports_access table.
    
    Args:
        name (str): Name of the person
        email (str): Email address (must be unique)
        granted_by (str): Person who granted the permission
    
    Returns:
        dict: Result with success status and record ID or error message
    """
    connection = connect_db()
    if not connection:
        #log('ERROR', "Failed to establish database connection for insert operation.")
        return {'success': False, 'error': 'Database connection failed'}
    
    cursor = None
    try:
        cursor = connection.cursor()
        
        query = """
            INSERT INTO alta_reports_access (name, email, granted_by)
            VALUES (%s, %s, %s)
            RETURNING id,name, email, granted_by, permission_granted_at
        """
        
        #log('INFO', f"Executing insert query for name: {name}, email: {email}")
        
        cursor.execute(query, (name, email, granted_by))
        result = cursor.fetchone()
        connection.commit()
        
        record_id = result[0]
        permission_granted_at = result[1]
        
        #log('INFO', f"Successfully inserted record with ID: {record_id}")
        return {
            'success': True, 
            'record_id': record_id,
            'permission_granted_at': permission_granted_at,
            'message': 'Record inserted successfully'
        }
        
    except psycopg2.IntegrityError as e:
        if connection:
            connection.rollback()
        if 'unique' in str(e).lower():
            #log('WARNING', f"Duplicate email address: {email}")
            return {'success': False, 'error': 'Email address already exists'}
        else:
            #log('ERROR', f"Integrity error during insert: {e}")
            return {'success': False, 'error': f'Data integrity error: {e}'}
    except psycopg2.Error as e:
        if connection:
            connection.rollback()
            #log('WARNING', "Database transaction rolled back due to error during insert.")
        #log('ERROR', f"Database error during insert: {e}")
        return {'success': False, 'error': f'Database error: {e}'}
    except Exception as e:
        #log('CRITICAL', f"An unexpected error occurred during insert: {e}")
        return {'success': False, 'error': f'Unexpected error: {e}'}
    finally:
        if cursor:
            cursor.close()
            #log('INFO', "Database cursor closed.")
        if connection:
            connection.close()
            #log('INFO', "Database connection closed.")


def delete_access_record(record_id):
    """
    Function to delete a record from alta_reports_access table.
    
    Args:
        record_id (int): ID of the record to delete
    
    Returns:
        dict: Result with success status and deleted record info or error message
    """
    connection = connect_db()
    if not connection:
        #log('ERROR', "Failed to establish database connection for delete operation.")
        return {'success': False, 'error': 'Database connection failed'}
    
    cursor = None
    try:
        cursor = connection.cursor()
        
        # First, get the record before deleting
        select_query = "SELECT * FROM alta_reports_access WHERE id = %s"
        cursor.execute(select_query, (record_id,))
        record = cursor.fetchone()
        
        if not record:
            return {'success': False, 'error': 'Record not found'}
        
        # Get column names from the SELECT query
        columns = [desc[0] for desc in cursor.description]
        deleted_record = dict(zip(columns, record))
        
        # Delete the record
        delete_query = "DELETE FROM alta_reports_access WHERE id = %s"
        cursor.execute(delete_query, (record_id,))
        connection.commit()
        
        #log('INFO', f"Successfully deleted record with ID: {record_id}")
        return {
            'success': True,
            'deleted_record': deleted_record,
            'message': 'Record deleted successfully'
        }
        
    except psycopg2.Error as e:
        if connection:
            connection.rollback()
            #log('WARNING', "Database transaction rolled back due to error during delete.")
        #log('ERROR', f"Database error during delete: {e}")
        return {'success': False, 'error': f'Database error: {e}'}
    except Exception as e:
        #log('CRITICAL', f"An unexpected error occurred during delete: {e}")
        return {'success': False, 'error': f'Unexpected error: {e}'}
    finally:
        if cursor:
            cursor.close()
            #log('INFO', "Database cursor closed.")
        if connection:
            connection.close()
            #log('INFO', "Database connection closed.")


def fetch_access_records(record_id=None, email=None, limit=None):
    """
    Function to fetch records from alta_reports_access table.
    
    Args:
        record_id (int, optional): Specific record ID to fetch
        email (str, optional): Email to filter by
        limit (int, optional): Maximum number of records to return
    
    Returns:
        dict: Result with success status and records or error message
    """
    connection = connect_db()
    if not connection:
        #log('ERROR', "Failed to establish database connection for fetch operation.")
        return {'success': False, 'error': 'Database connection failed'}
    
    cursor = None
    try:
        cursor = connection.cursor()
        
        query = "SELECT * FROM alta_reports_access"
        conditions = []
        values = []
        
        if record_id is not None:
            conditions.append("id = %s")
            values.append(record_id)
        
        if email is not None:
            conditions.append("email = %s")
            values.append(email)
        
        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        
        query += " ORDER BY permission_granted_at DESC"
        
        if limit is not None:
            query += f" LIMIT {limit}"
        
        #log('INFO', f"Executing fetch query: {query}")
        if values:
            pass
            #log('INFO', f"Query values: {values}")
        
        cursor.execute(query, values)
        results = cursor.fetchall()
        
        # Get column names
        column_names = [desc[0] for desc in cursor.description]
        
        # Convert results to list of dictionaries
        records = []
        for row in results:
            record_dict = dict(zip(column_names, row))
            # Convert datetime to ISO format for JSON serialization
            if record_dict.get('permission_granted_at'):
                record_dict['permission_granted_at'] = record_dict['permission_granted_at'].isoformat()
            records.append(record_dict)
        
        #log('INFO', f"Successfully fetched {len(records)} records")
        return {
            'success': True,
            'records': records,
            'count': len(records),
            'message': f'Fetched {len(records)} records successfully'
        }
        
    except psycopg2.Error as e:
        #log('ERROR', f"Database error during fetch: {e}")
        return {'success': False, 'error': f'Database error: {e}'}
    except Exception as e:
        #log('CRITICAL', f"An unexpected error occurred during fetch: {e}")
        return {'success': False, 'error': f'Unexpected error: {e}'}
    finally:
        if cursor:
            cursor.close()
            #log('INFO', "Database cursor closed.")
        if connection:
            connection.close()
            #log('INFO', "Database connection closed.")


# Flask Routes

@app.route('/insert_access', methods=['POST'])
def insert_access_endpoint():
    """
    Flask endpoint to insert a new access record.
    Expects JSON payload with name, email, and granted_by.
    """
    #log('INFO', "Received request to /insert_access endpoint.")
    data = request.get_json()
    
    if not data or not isinstance(data, dict):
        #log('WARNING', "Invalid input for /insert_access. Expecting a dictionary.")
        return jsonify({'error': "Invalid input. Expecting a dictionary."}), 400
    
    required_fields = ['name', 'email', 'granted_by']
    for field in required_fields:
        if field not in data:
            #log('WARNING', f"Missing required field: {field}")
            return jsonify({'error': f"Missing required field: {field}"}), 400
    
    name = data['name']
    email = data['email']
    granted_by = data['granted_by']
    
    result = insert_access_record(name, email, granted_by)
    
    if result['success']:
        return jsonify(result), 201
    else:
        return jsonify(result), 400


@app.route('/delete_access/<int:record_id>', methods=['DELETE'])
def delete_access_endpoint(record_id):
    """
    Flask endpoint to delete an access record.
    """
    #log('INFO', f"Received request to /delete_access/{record_id} endpoint.")
    
    result = delete_access_record(record_id)
    
    if result['success']:
        return jsonify(result), 200
    else:
        return jsonify(result), 404


@app.route('/fetch_access', methods=['GET'])
def fetch_access_endpoint():
    """
    Flask endpoint to fetch access records.
    Optional query parameters: record_id, email, limit
    """
    #log('INFO', "Received request to /fetch_access endpoint.")
    
    record_id = request.args.get('record_id', type=int)
    email = request.args.get('email')
    limit = request.args.get('limit', type=int)
    
    result = fetch_access_records(record_id, email, limit)
    
    if result['success']:
        return jsonify(result), 200
    else:
        return jsonify(result), 500


@app.route('/health', methods=['GET'])
def health_check():
    """
    Health check endpoint to verify API and database connectivity.
    """
    #log('INFO', "Health check requested.")
    
    connection = connect_db()
    if connection:
        connection.close()
        return jsonify({'status': 'healthy', 'database': 'connected'}), 200
    else:
        return jsonify({'status': 'unhealthy', 'database': 'disconnected'}), 500


if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    #log("INFO", f"Flask database API is starting up on port {port}.", data={"host": "127.0.0.1", "port": port})
    # Use threaded=False and processes=1 to avoid Windows threading issues
    app.run(host="127.0.0.1", port=port, debug=True, threaded=False, processes=1)
