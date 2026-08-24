from flask import Flask, request, jsonify
import http.client
import logging
from azure.storage.blob import BlobServiceClient, generate_blob_sas, BlobSasPermissions
from datetime import datetime, timedelta
import os
import psycopg2

app = Flask(__name__)


api_version = "2024-05-01"

global api_key, text_translation_endpoint, document_translation_endpoint, region, storage_connection_string
# Global variables for settings
api_key = None
text_translation_endpoint = None
document_translation_endpoint = None
region = None
storage_connection_string = None

def retrieve_settings():
    global api_key, text_translation_endpoint, document_translation_endpoint, region, storage_connection_string
    
    try:
        admin_id = 1
        logging.info("Starting settings retrieval...")  # Debug log

        # Database connection
        connection = psycopg2.connect(
            database= os.getenv('DB_NAME'),  # 'settings_db' is the default if env variable is not set
            user=os.getenv('DB_USER'),
            password= os.getenv('DB_PASSWORD'),
            host= os.getenv('DB_HOST'),
            port= os.getenv('DB_PORT')
        )
        cursor = connection.cursor()

        query = """
        SELECT key, text_translation_endpoint, document_translation_endpoint, region, storage_connection_string
        FROM settings
        WHERE admin_id = %s;
        """
        cursor.execute(query, (admin_id,))
        result = cursor.fetchone()

        if not result:
            logging.error("No settings found")  # Debug log
            return jsonify({"error": f"No settings found for Admin_id {admin_id}."}), 404

        # Set global variables
        api_key = result[0]
        text_translation_endpoint = result[1]
        document_translation_endpoint = result[2]
        region = result[3]
        storage_connection_string = result[4]

        logging.info(f"Settings retrieved successfully: document_translation_endpoint={document_translation_endpoint}")  # Debug log

        cursor.close()
        connection.close()

        return jsonify({
            'status': 'success',
            'message': 'Settings retrieved successfully'
        }), 200

    except Exception as e:
        logging.error(f"Settings retrieval error: {str(e)}")  # Debug log
        return jsonify({"error": str(e)}), 500


# Function to check the translation job status
def check_translation_status(job_id):
    try:
        if not document_translation_endpoint:
            raise ValueError("document_translation_endpoint is not set")
            
        domain = document_translation_endpoint.split("//")[1].strip("/")
        if not domain:
            raise ValueError("Invalid document_translation_endpoint format")
            
        if not api_key:
            raise ValueError("api_key is not set")

        # Initialize HTTPS connection
        conn = http.client.HTTPSConnection(domain)

        # Prepare request path
        path = f"/translator/document/batches/{job_id}?api-version={api_version}"
        headers = {
            'Ocp-Apim-Subscription-Key': api_key
        }

        # Make GET request
        conn.request("GET", path, headers=headers)
        response = conn.getresponse()
        data = response.read().decode("utf-8")
        conn.close()

        # Add logging to see the response
        logging.info(f"Azure API Response: {data}")

        return {
            "status": response.status,
            "data": data
        }
    except Exception as e:
        logging.error(f"Error checking translation status: {str(e)}")
        return {
            "status": "error",
            "message": str(e)
        }


# Function to generate SAS URLs for all files in a specified container along with their names
def get_all_blob_sas_urls(container_name):
    try:
        if not storage_connection_string:
            raise ValueError("storage_connection_string is not set")
            
        # Split the connection string into key-value pairs
        parts = dict(item.split("=", 1) for item in storage_connection_string.split(";"))
        account_name = parts.get("AccountName")
        account_key = parts.get("AccountKey")
        
        if not account_name or not account_key:
            raise ValueError("Missing AccountName or AccountKey in connection string")
        # Define the SAS token expiration time
        sas_token_expiry = datetime.utcnow() + timedelta(hours=1)
        blob_service_client = BlobServiceClient(account_url=f"https://{account_name}.blob.core.windows.net", credential=account_key)


        # List all blobs in the specified container
        container_client = blob_service_client.get_container_client(container_name)
        blob_list = container_client.list_blobs()

        sas_data = []

        # Generate SAS URL for each blob and include the file name
        for blob in blob_list:
            blob_name = blob.name
            sas_token = generate_blob_sas(
                account_name=account_name,
                container_name=container_name,
                blob_name=blob_name,
                account_key=account_key,
                permission=BlobSasPermissions(read=True),
                expiry=sas_token_expiry
            )
            sas_url = f"https://{account_name}.blob.core.windows.net/{container_name}/{blob_name}?{sas_token}"

            # Append file name and SAS URL as a dictionary
            sas_data.append({
                "file_name": blob_name,
                "sas_url": sas_url
            })

        return sas_data
    except Exception as e:
        logging.error(f"Error generating SAS URLs: {str(e)}")
        return []


@app.route('/translation_status', methods=['POST'])
def translation_status():
    try:
        # First get settings
        logging.info("Starting translation status check...")
        settings_result = retrieve_settings()
        if isinstance(settings_result, tuple) and settings_result[1] != 200:
            logging.error(f"Settings retrieval failed: {settings_result}")
            return settings_result

        # Get request parameters
        job_id = request.form.get('job_id')
        target_container_name = request.form.get('target_container_name')
        
        logging.info(f"Received request with job_id={job_id}, target_container={target_container_name}")

        if not job_id or not target_container_name:
            return jsonify({"error": "job_id and target_container_name are required"}), 400

        # Get translation status
        status_response = check_translation_status(job_id)
        logging.info(f"Translation status response: {status_response}")

        if status_response.get('status') == 'error':
            return jsonify(status_response), 500

        # Parse response data
        try:
            import json
            data = json.loads(status_response['data'])
            logging.info(f"Parsed status data: {data}")
            
            # Check all possible status fields and their variations
            status = None
            if 'status' in data:
                status = data['status']
            elif 'Status' in data:
                status = data['Status']
            elif 'summary' in data and 'status' in data['summary']:
                status = data['summary']['status']
            elif 'summary' in data and 'Status' in data['summary']:
                status = data['summary']['Status']

            # Log the actual status for debugging
            logging.info(f"Extracted status: {status}")

            # Check if status exists and handle accordingly
            if status:
                status_lower = status.lower()
                if 'succeeded' in status_lower or 'completed' in status_lower:
                    # Get SAS URLs
                    sas_data = get_all_blob_sas_urls(target_container_name)
                    if not sas_data:
                        return jsonify({
                            'status': 'error',
                            'message': 'No files found or failed to generate SAS URLs'
                        }), 500
                    
                    return jsonify({
                        'status': 'success',
                        'translation_status': 'Succeeded',
                        'sas_data': sas_data
                    }), 200
                    
                elif 'failed' in status_lower or 'cancelled' in status_lower or 'error' in status_lower:
                    return jsonify({
                        'status': 'error',
                        'message': f'Translation {status}',
                        'details': data.get('error', {}).get('message', 'No error details available')
                    }), 400
                    
                elif 'running' in status_lower or 'in progress' in status_lower or 'notstarted' in status_lower:
                    # Add more details about the progress if available
                    progress = data.get('summary', {}).get('progress', 'unknown')
                    return jsonify({
                        'status': 'pending',
                        'message': 'Translation in progress',
                        'progress': progress,
                        'current_status': status
                    }), 200
                else:
                    return jsonify({
                        'status': 'pending',
                        'message': f'Unknown status: {status}',
                        'raw_status': status
                    }), 200
            else:
                # If we can't find a status, return the raw response for debugging
                return jsonify({
                    'status': 'error',
                    'message': 'Could not determine translation status',
                    'raw_response': data
                }), 500

        except json.JSONDecodeError as e:
            logging.error(f"JSON parsing error: {e}, raw data: {status_response['data']}")
            return jsonify({
                'status': 'error',
                'message': 'Invalid response from translation service',
                'raw_data': status_response['data']
            }), 500

    except Exception as e:
        logging.error(f"Unexpected error: {str(e)}")
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500
    
    
if __name__ == '__main__':
    app.run(debug=True)
