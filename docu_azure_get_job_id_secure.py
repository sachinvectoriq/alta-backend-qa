import logging
import json
import requests
from datetime import datetime, timedelta
from azure.storage.blob import BlobServiceClient, generate_blob_sas, BlobSasPermissions
from flask import Flask, request, jsonify
import time
import psycopg2
import os



# Setup Flask app
app = Flask(__name__)

# Setup logging
logging.basicConfig(level=logging.INFO)


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






# Global variables
connection_string = None
api_key = None
endpoint = None
document_translation_endpoint = None
blob_service_client = None
base_path = None
account_name = None
account_key = None

# Hardcoded Admin ID
admin_id = '1'
# Construct the full URL with admin_id as a query parameter
# full_url = f"{retrieve_settings_url}?admin_id={admin_id}"


def get_settings():
    global connection_string, api_key, endpoint, document_translation_endpoint, blob_service_client, base_path
    try:
        # Database connection details
        host = os.getenv('DB_HOST')
        database = os.getenv('DB_NAME')
        user = os.getenv('DB_USER')
        password = os.getenv('DB_PASSWORD')
        port = os.getenv('DB_PORT')

        # Establish connection to PostgreSQL
        conn = psycopg2.connect(
            host=host,
            database=database,
            user=user,
            password=password,
            port=port,
            sslmode='require'  # Ensure secure connection with Cosmos DB for PostgreSQL
        )

        # Create a cursor object to interact with the database
        cursor = conn.cursor()

        # SQL query to fetch settings for the given admin_id
        query = """
        SELECT key, text_translation_endpoint, document_translation_endpoint, region, storage_connection_string
        FROM settings
        WHERE admin_id = %s;
        """
        cursor.execute(query, (admin_id,))
        result = cursor.fetchone()

        # Check if result is found
        if result:
            api_key, endpoint, document_translation_endpoint, region, connection_string = result
            base_path = f"{document_translation_endpoint}/translator/document/batches"

            # Check if all necessary settings were retrieved
            if not all([connection_string, api_key, endpoint, document_translation_endpoint, base_path]):
                logging.error("Missing required settings.")
                return False

            # Initialize BlobServiceClient
            blob_service_client = BlobServiceClient.from_connection_string(connection_string)
            logging.info("Settings retrieved and blob client initialized.")
            return True
        else:
            logging.error("No settings found for the specified admin_id.")
            return False

    except psycopg2.Error as e:
        logging.error(f"Database error: {e}")
        return False
    finally:
        # Close the cursor and connection
        if 'cursor' in locals():
            cursor.close()
        if 'conn' in locals():
            conn.close()


def parse_storage_account_details():
    global account_name, account_key, connection_string
    try:
        account_name_start = connection_string.find("AccountName=") + len("AccountName=")
        account_name_end = connection_string.find(";", account_name_start)
        account_key_start = connection_string.find("AccountKey=") + len("AccountKey=")
        account_key_end = connection_string.find(";", account_key_start)

        account_name = connection_string[account_name_start:account_name_end]
        account_key = connection_string[account_key_start:account_key_end]

        logging.info(f"Storage account name extracted: {account_name}")
        logging.info("Storage account key extracted.")
    except Exception as ex:
        logging.error(f"Failed to parse storage account details: {ex}")



# Assuming blob_service_client is defined globally elsewhere in your code
# If not, you might want to initialize it within these functions or pass it as a parameter.

def create_container(container_name):
    try:
        container_client = blob_service_client.create_container(container_name)
        logging.info(f"Container '{container_name}' created successfully.")
        return container_name
    except Exception as ex:
        logging.error(f"An error occurred while creating the container '{container_name}': {ex}")
        return str(ex)

def generate_container_names():
    global source_container_name, target_container_name, glossary_container_name

    timestamp = datetime.utcnow().strftime('%Y%m%d%H%M%S')
    
    source_container_name = f"source-{timestamp}"
    target_container_name = f"destination-{timestamp}"
    glossary_container_name = f"glossary-{timestamp}"

    # Create containers
    create_container(source_container_name)
    create_container(target_container_name)
    create_container(glossary_container_name)

def upload_blob(file_name, file_content, container_name, target_language_code):
    try:
        # Modify the file name to include the target language code
        modified_file_name = f"{file_name.rsplit('.', 1)[0]}-{target_language_code}.{file_name.rsplit('.', 1)[1]}"

        # Get container and blob clients
        container_client = blob_service_client.get_container_client(container_name)
        blob_client = container_client.get_blob_client(modified_file_name)

        # Upload the blob
        blob_client.upload_blob(file_content, overwrite=True)
        logging.info(f"File '{modified_file_name}' uploaded to container '{container_name}' successfully.")
        return f"File '{modified_file_name}' uploaded successfully."
    except Exception as ex:
        logging.error(f"An error occurred: {ex}")
        return str(ex)

def upload_blob2(file_name, file_content, container_name):
    try:
        container_client = blob_service_client.get_container_client(container_name)
        blob_client = container_client.get_blob_client(file_name)
        blob_client.upload_blob(file_content, overwrite=True)
        logging.info(f"File '{file_name}' uploaded to container '{container_name}' successfully.")
        return f"File '{file_name}' uploaded successfully."
    except Exception as ex:
        logging.error(f"An error occurred: {ex}")
        return str(ex)

# The above functions can be called in your main function or route handler as needed.


# Assuming api_key, endpoint, and document_translation_endpoint are defined globally elsewhere in your code

def get_supported_languages():
    try:
        url = f"{endpoint}languages?api-version=3.0"
        headers = {
            'Ocp-Apim-Subscription-Key': api_key,
            'Content-Type': 'application/json'
        }
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        logging.error(f"Failed to retrieve supported languages: {str(e)}")
        raise e

def get_language_code(language_name):
    languages = get_supported_languages()
    if 'translation' in languages:
        for key, value in languages['translation'].items():
            if value['name'].lower() == language_name.lower() or value['nativeName'].lower() == language_name.lower():
                return key
    return None


def docu_trans_azure2_secure():
    logging.info('Processing HTTP request.')



    auth_error = validate_bearer_token(request, 'A7x!G2p@Q9#L')  # Replace 'A7x!G2p@Q9#L' with your actual token
    if auth_error:
        return auth_error



  

    # Ensure settings are retrieved
    if not get_settings():
        return jsonify({"message": "Failed to retrieve settings."}), 500

    # Parse the storage account details
    parse_storage_account_details()

    generate_container_names()  # Dynamically create new containers

    source_language_name = request.form.get('source_language')
    target_language_name = request.form.get('target_language')


    if not source_language_name or not target_language_name:
        return jsonify({"message": "Please provide both source_language and target_language in the request."}), 400

    source_language_code = get_language_code(source_language_name)
    target_language_code = get_language_code(target_language_name)

    if not source_language_code or not target_language_code:
        return jsonify({"message": "One or both languages are not supported."}), 404

    if 'file' not in request.files and 'glossary_file' not in request.files:
        return jsonify({"message": "No files part in the request."}), 400

    files = request.files.getlist('file')
    glossary_files = request.files.getlist('glossary_file')

    results = []
    for file in files:
        file_content = file.read()
        
        # Call the upload_blob function with the target language code
        result = upload_blob(file.filename, file_content, source_container_name, target_language_code)
        results.append(result)

    # Handle glossary file uploads
    if glossary_files:
        for glossary_file in glossary_files:
            glossary_content = glossary_file.read()
            result = upload_blob2("glossary.csv", glossary_content, glossary_container_name)
            results.append(result)

        # Detect the glossary format based on file extension
        glossary_file_extension = "csv"  # Default to CSV
        if glossary_files[0].filename.endswith('.tsv'):
            glossary_file_extension = "tsv"
        elif glossary_files[0].filename.endswith('.csv'):
            glossary_file_extension = "csv"

    base_path = f"{document_translation_endpoint}translator/document/batches"
    route = '?api-version=2024-05-01'
    constructed_url = base_path + route

    # Prepare payload
    if glossary_files:
        payload = {
            "inputs": [
                {
                    "source": {
                        "sourceUrl": f"https://{account_name}.blob.core.windows.net/{source_container_name}",
                        "language": source_language_code
                    },
                    "targets": [
                        {
                            "targetUrl": f"https://{account_name}.blob.core.windows.net/{target_container_name}",
                            "language": target_language_code,
                            "glossaries": [
                                {
                                    "glossaryUrl": f"https://{account_name}.blob.core.windows.net/{glossary_container_name}/glossary.csv",
                                    "format": glossary_file_extension
                                }
                            ]
                        }
                    ]
                }
            ]
        }
    else:
        payload = {
            "inputs": [
                {
                    "source": {
                        "sourceUrl": f"https://{account_name}.blob.core.windows.net/{source_container_name}",
                        "language": source_language_code
                    },
                    "targets": [
                        {
                            "targetUrl": f"https://{account_name}.blob.core.windows.net/{target_container_name}",
                            "language": target_language_code
                        }
                    ]
                }
            ]
        }

    headers = {
        'Ocp-Apim-Subscription-Key': api_key,
        'Content-Type': 'application/json'
    }

    try:
        response = requests.post(constructed_url, headers=headers, json=payload)
        response.raise_for_status()
        job_id = response.json().get('id')  # Get the job ID from the response
        return jsonify({"message": "Translation job submitted successfully.", "job_id": job_id,"destination container name": target_container_name}), 200
    except requests.exceptions.RequestException as e:
        logging.error(f"Request to Translator API failed: {str(e)}")
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500

if __name__ == '__main__':
    app.run(debug=True)
