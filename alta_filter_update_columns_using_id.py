from flask import Flask, request, jsonify
import psycopg2
from psycopg2 import sql
from datetime import datetime
import os

app = Flask(__name__)

# Database connection parameters
DB_CONFIG = {
    'host': 'c-settings-details.4frco7jk32qfsk.postgres.cosmos.azure.com',
    'database': 'settings_db',
    'user': 'citus',
    'password': 'password@123',
    'port': 5432
}

def get_db_connection():
    """Create and return a database connection"""
    conn = psycopg2.connect(**DB_CONFIG)
    return conn

@app.route('/update_filter', methods=['PUT'])
def update_filter():
    try:
        # Get id parameter (required)
        filter_id = request.args.get('id')
        if not filter_id:
            return jsonify({"error": "Missing required parameter: id"}), 400
        
        # Get optional parameters
        modifier = request.args.get('modifier')
        value = request.args.get('value')
        system_prompt = request.args.get('system_prompt')
        user_prompt = request.args.get('user_prompt')
        created_by = request.args.get('created_by')
        
        # Prepare update fields
        update_fields = {}
        if modifier is not None:
            update_fields['modifier'] = modifier
        if value is not None:
            update_fields['value'] = value
        if system_prompt is not None:
            update_fields['system_prompt'] = system_prompt
        if user_prompt is not None:
            update_fields['user_prompt'] = user_prompt
        if created_by is not None:
            update_fields['created_by'] = created_by
        
        # Add updated_at timestamp
        update_fields['updated_at'] = datetime.now()
        
        # If no fields to update, return error
        if not update_fields:
            return jsonify({"error": "No update parameters provided"}), 400
        
        # Connect to the database
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Build dynamic SQL query
        query = sql.SQL("UPDATE alta_filters SET {} WHERE id = {} RETURNING id, modifier, system_prompt, user_prompt, value").format(
            sql.SQL(', ').join(
                sql.SQL("{} = {}").format(
                    sql.Identifier(k),
                    sql.Literal(v)
                ) for k, v in update_fields.items()
            ),
            sql.Literal(filter_id)
        )
        
        # Execute query and fetch updated row
        cursor.execute(query)
        updated_row = cursor.fetchone()
        
        # Check if any rows were affected
        if cursor.rowcount == 0:
            conn.rollback()
            cursor.close()
            conn.close()
            return jsonify({"error": f"No filter found with id {filter_id}"}), 404
        
        # Commit changes
        conn.commit()
        cursor.close()
        conn.close()

        # Prepare updated data response
        updated_data = {
            "id": updated_row[0],
            "modifier": updated_row[1],
            "system": updated_row[2],  # Adjusted key names as per your required response
            "user": updated_row[3],
            "value": updated_row[4]
        }

        return jsonify({
            "data": updated_data,
            "message": f"Filter with id {filter_id} updated successfully",
            "rows_affected": cursor.rowcount
        }), 200
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500




if __name__ == '__main__':
    app.run(debug=True)
