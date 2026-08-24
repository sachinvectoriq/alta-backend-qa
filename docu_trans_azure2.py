import logging
import json
import requests
from datetime import datetime, timedelta
from azure.storage.blob import BlobServiceClient, generate_blob_sas, BlobSasPermissions
from flask import Flask, request, jsonify
import time
import psycopg2
import os

# Assuming logging_config.py exists and defines log and flush functions
from logging_config import log, flush


# Setup Flask app
app = Flask(__name__)

# Setup logging (this line is still here but actual logging will use `log` function)
logging.basicConfig(level=logging.INFO)

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


def get_settings():
    global connection_string, api_key, endpoint, document_translation_endpoint, blob_service_client, base_path
    # Determine user_name for logging context
    user_name = request.form.get('user', request.remote_addr if request else "unknown")
    try:
        log("INFO", "Attempting to retrieve application settings from database.", user_name=user_name)
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
        log("INFO", "Successfully connected to settings database.", user_name=user_name, data={"db_host": host, "db_name": database})

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
                log("ERROR", "Missing required settings after database retrieval.", user_name=user_name)
                flush()
                return False

            # Initialize BlobServiceClient
            blob_service_client = BlobServiceClient.from_connection_string(connection_string)
            log("INFO", "Settings retrieved and blob client initialized successfully.", user_name=user_name)
            return True
        else:
            log("ERROR", f"No settings found for admin_id: {admin_id}.", user_name=user_name)
            flush()
            return False

    except psycopg2.Error as e:
        log("ERROR", f"Database error during settings retrieval: {e}", user_name=user_name, data={"error_details": str(e)})
        flush()
        return False
    except ValueError as e: # Catch errors for invalid environment variables (e.g. port)
        log("CRITICAL", f"Configuration error: Invalid environment variable for database connection. {e}", user_name=user_name, data={"error_details": str(e)})
        flush()
        return False
    except Exception as e:
        log("CRITICAL", f"An unexpected error occurred during settings retrieval: {e}", user_name=user_name, data={"error_type": type(e).__name__, "error_details": str(e)})
        flush()
        return False
    finally:
        # Close the cursor and connection
        if 'cursor' in locals() and cursor:
            cursor.close()
        if 'conn' in locals() and conn:
            conn.close()
            log("INFO", "Closed database connection after settings retrieval.", user_name=user_name)
            flush()


def parse_storage_account_details():
    global account_name, account_key, connection_string
    # Determine user_name for logging context
    user_name = request.form.get('user', request.remote_addr if request else "unknown")
    try:
        if not connection_string:
            log("ERROR", "Connection string is not set, cannot parse storage account details.", user_name=user_name)
            raise ValueError("Storage connection string not available.")

        account_name_start = connection_string.find("AccountName=") + len("AccountName=")
        account_name_end = connection_string.find(";", account_name_start)
        account_key_start = connection_string.find("AccountKey=") + len("AccountKey=")
        account_key_end = connection_string.find(";", account_key_start)

        account_name = connection_string[account_name_start:account_name_end]
        account_key = connection_string[account_key_start:account_key_end]

        log("INFO", f"Storage account name extracted: {account_name}", user_name=user_name)
        log("INFO", "Storage account key extracted (sensitive data not logged).", user_name=user_name)
    except Exception as ex:
        log("ERROR", f"Failed to parse storage account details: {ex}", user_name=user_name, data={"error_details": str(ex)})
        flush()
        raise


def create_container(container_name):
    # Determine user_name for logging context
    user_name = request.form.get('user', request.remote_addr if request else "unknown")
    try:
        if not blob_service_client:
            log("ERROR", "BlobServiceClient is not initialized, cannot create container.", user_name=user_name)
            return False # Indicate failure instead of raising for this helper
        container_client = blob_service_client.create_container(container_name)
        log("INFO", f"Container '{container_name}' created successfully.", user_name=user_name)
        return container_name # Original code returned name on success
    except Exception as ex:
        log("ERROR", f"An error occurred while creating the container '{container_name}': {ex}", user_name=user_name, data={"container": container_name, "error_details": str(ex)})
        flush()
        return str(ex) # Original code returned error string on failure

def generate_container_names():
    global source_container_name, target_container_name, glossary_container_name
    # Determine user_name for logging context
    user_name = request.form.get('user', request.remote_addr if request else "unknown")

    timestamp = datetime.utcnow().strftime('%Y%m%d%H%M%S')
    
    source_container_name = f"source-{timestamp}"
    target_container_name = f"destination-{timestamp}"
    glossary_container_name = f"glossary-{timestamp}"

    log("INFO", f"Generated container names: source={source_container_name}, target={target_container_name}, glossary={glossary_container_name}.", user_name=user_name)

    # Create containers
    result_source = create_container(source_container_name)
    if not (isinstance(result_source, str) and result_source == source_container_name): # Check if creation failed
        log("WARNING", f"Failed to create source container: {result_source}", user_name=user_name, data={"container": source_container_name})

    result_target = create_container(target_container_name)
    if not (isinstance(result_target, str) and result_target == target_container_name):
        log("WARNING", f"Failed to create target container: {result_target}", user_name=user_name, data={"container": target_container_name})

    result_glossary = create_container(glossary_container_name)
    if not (isinstance(result_glossary, str) and result_glossary == glossary_container_name):
        log("WARNING", f"Failed to create glossary container: {result_glossary}", user_name=user_name, data={"container": glossary_container_name})


def upload_blob(file_name, file_content, container_name, target_language_code):
    # Determine user_name for logging context
    user_name = request.form.get('user', request.remote_addr if request else "unknown")
    try:
        if not blob_service_client:
            log("ERROR", "BlobServiceClient is not initialized, cannot upload blob.", user_name=user_name)
            return "BlobServiceClient not initialized."

        # Modify the file name to include the target language code
        name_parts = file_name.rsplit('.', 1)
        if len(name_parts) == 2:
            modified_file_name = f"{name_parts[0]}-{target_language_code}.{name_parts[1]}"
        else:
            modified_file_name = f"{file_name}-{target_language_code}" # Fallback if no extension

        # Get container and blob clients
        container_client = blob_service_client.get_container_client(container_name)
        blob_client = container_client.get_blob_client(modified_file_name)

        # Upload the blob
        blob_client.upload_blob(file_content, overwrite=True)
        log("INFO", f"File '{modified_file_name}' uploaded to container '{container_name}' successfully.", user_name=user_name, data={"file": modified_file_name, "container": container_name})
        return f"File '{modified_file_name}' uploaded successfully."
    except Exception as ex:
        log("ERROR", f"An error occurred during blob upload: {ex}", user_name=user_name, data={"file": file_name, "container": container_name, "error_details": str(ex)})
        flush()
        return str(ex)

def upload_blob2(file_name, file_content, container_name):
    # Determine user_name for logging context
    user_name = request.form.get('user', request.remote_addr if request else "unknown")
    try:
        if not blob_service_client:
            log("ERROR", "BlobServiceClient is not initialized, cannot upload glossary blob.", user_name=user_name)
            return "BlobServiceClient not initialized."

        container_client = blob_service_client.get_container_client(container_name)
        blob_client = container_client.get_blob_client(file_name)
        blob_client.upload_blob(file_content, overwrite=True)
        log("INFO", f"File '{file_name}' uploaded to container '{container_name}' successfully.", user_name=user_name, data={"file": file_name, "container": container_name})
        return f"File '{file_name}' uploaded successfully."
    except Exception as ex:
        log("ERROR", f"An error occurred during glossary blob upload: {ex}", user_name=user_name, data={"file": file_name, "container": container_name, "error_details": str(ex)})
        flush()
        return str(ex)


def get_supported_languages():
    # Determine user_name for logging context
    user_name = request.form.get('user', request.remote_addr if request else "unknown")
    try:
        if not endpoint or not api_key:
            log("ERROR", "Translator API endpoint or API key not set. Cannot get supported languages.", user_name=user_name)
            raise ValueError("Translator API configuration missing.")

        url = f"{endpoint}languages?api-version=3.0"
        headers = {
            'Ocp-Apim-Subscription-Key': api_key,
            'Content-Type': 'application/json'
        }
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        log("INFO", "Successfully retrieved supported languages from Translator API.", user_name=user_name, data={"api_url": url})
        return response.json()
    except requests.exceptions.RequestException as e:
        log("ERROR", f"Failed to retrieve supported languages from Translator API: {str(e)}", user_name=user_name, data={"api_url": url, "error_details": str(e)})
        flush()
        raise e
    except Exception as e:
        log("CRITICAL", f"An unexpected error occurred while fetching supported languages: {e}", user_name=user_name, data={"error_type": type(e).__name__, "error_details": str(e)})
        flush()
        raise e


def get_language_code(language_name):
    # Determine user_name for logging context
    user_name = request.form.get('user', request.remote_addr if request else "unknown")
    languages = get_supported_languages()
    if languages and 'translation' in languages:
        for key, value in languages['translation'].items():
            if value['name'].lower() == language_name.lower() or value['nativeName'].lower() == language_name.lower():
                log("INFO", f"Resolved language '{language_name}' to code '{key}'.", user_name=user_name)
                return key
    log("WARNING", f"Could not find language code for language name: '{language_name}'.", user_name=user_name)
    return None

def generate_sas_url(account_name, account_key, container_name, blob_name):
    # Determine user_name for logging context
    user_name = request.form.get('user', request.remote_addr if request else "unknown")
    try:
        blob_service_client = BlobServiceClient(
            account_url=f"https://{account_name}.blob.core.windows.net",
            credential=account_key
        )
        sas_expiry = datetime.utcnow() + timedelta(hours=1)
        sas_token = generate_blob_sas(
            account_name=account_name,
            container_name=container_name,
            blob_name=blob_name,
            account_key=account_key,
            permission=BlobSasPermissions(read=True),
            expiry=sas_expiry
        )
        blob_client = blob_service_client.get_blob_client(container=container_name, blob=blob_name)
        sas_url = f"{blob_client.url}?{sas_token}"
        log("DEBUG", f"Generated SAS URL for blob '{blob_name}' in container '{container_name}'.", user_name=user_name, data={"blob": blob_name, "container": container_name})
        return sas_url
    except Exception as e:
        log("ERROR", f"An error occurred while generating SAS URL for blob '{blob_name}': {e}", user_name=user_name, data={"blob": blob_name, "container": container_name, "error_details": str(e)})
        flush()
        raise e

def get_blob_sas_urls(account_name, account_key, container_name):
    # Determine user_name for logging context
    user_name = request.form.get('user', request.remote_addr if request else "unknown")
    blob_service_client_list = BlobServiceClient(
        account_url=f"https://{account_name}.blob.core.windows.net",
        credential=account_key
    )
    container_client = blob_service_client_list.get_container_client(container_name)
    sas_urls = {}
    try:
        for blob in container_client.list_blobs():
            blob_name = blob.name
            sas_url = generate_sas_url(account_name, account_key, container_name, blob_name)
            sas_urls[blob_name] = sas_url
        log("INFO", f"Generated SAS URLs for {len(sas_urls)} blobs in container '{container_name}'.", user_name=user_name, data={"container": container_name, "count": len(sas_urls)})
    except Exception as e:
        log("ERROR", f"An error occurred while generating SAS URLs for container '{container_name}': {e}", user_name=user_name, data={"container": container_name, "error_details": str(e)})
        flush()
        raise e
    return sas_urls

def check_translation_status(job_id):
    # Determine user_name for logging context
    user_name = request.form.get('user', request.remote_addr if request else "unknown")
    try:
        if not document_translation_endpoint or not api_key:
            log("ERROR", "Document Translation endpoint or API key not set. Cannot check translation status.", user_name=user_name)
            raise ValueError("Document Translation API configuration missing.")

        url = f"{document_translation_endpoint}translator/document/batches/{job_id}?api-version=2024-05-01"
        headers = {
            'Ocp-Apim-Subscription-Key': api_key,
        }
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        log("INFO", f"Checked translation status for job ID '{job_id}'. Current status: {response.json().get('status')}", user_name=user_name, data={"job_id": job_id, "status": response.json().get('status')})
        return response.json()
    except requests.exceptions.RequestException as e:
        log("ERROR", f"Error checking translation status for job ID '{job_id}': {str(e)}", user_name=user_name, data={"job_id": job_id, "error_details": str(e)})
        flush()
        raise e
    except Exception as e:
        log("CRITICAL", f"An unexpected error occurred while checking translation status for job ID '{job_id}': {e}", user_name=user_name, data={"job_id": job_id, "error_type": type(e).__name__, "error_details": str(e)})
        flush()
        raise e


@app.route('/docu_trans_azure2', methods=['POST'])
def docu_trans_azure2():
    # Determine user_name for logging context
    user_name = request.form.get('user', request.remote_addr)
    log("INFO", 'Processing HTTP request for document translation.', user_name=user_name, data={"ip": request.remote_addr})
    flush()

    # Ensure settings are retrieved
    if not get_settings():
        log("ERROR", "Failed to retrieve settings during request processing. Aborting.", user_name=user_name)
        flush()
        return jsonify({"message": "Failed to retrieve settings."}), 500

    # Parse the storage account details
    try:
        parse_storage_account_details()
    except Exception as e:
        log("CRITICAL", f"Failed to parse storage account details. Aborting translation process: {e}", user_name=user_name, data={"error_details": str(e)})
        flush()
        return jsonify({"message": f"Server configuration error: {e}"}), 500


    generate_container_names()  # Dynamically create new containers

    source_language_name = request.form.get('source_language')
    target_language_name = request.form.get('target_language')


    if not source_language_name or not target_language_name:
        log("WARNING", "Missing source_language or target_language in request.", user_name=user_name, data={"source_lang_provided": bool(source_language_name), "target_lang_provided": bool(target_language_name)})
        flush()
        return jsonify({"message": "Please provide both source_language and target_language in the request."}), 400

    source_language_code = get_language_code(source_language_name)
    target_language_code = get_language_code(target_language_name)

    if not source_language_code or not target_language_code:
        log("WARNING", f"One or both languages are not supported. Source: '{source_language_name}', Target: '{target_language_name}'.", user_name=user_name)
        flush()
        return jsonify({"message": "One or both languages are not supported."}), 404

    if 'file' not in request.files and 'glossary_file' not in request.files:
        log("WARNING", "No files or glossary files found in the request.", user_name=user_name)
        flush()
        return jsonify({"message": "No files part in the request."}), 400

    files = request.files.getlist('file')
    glossary_files = request.files.getlist('glossary_file')

    results = []
    for file in files:
        file_content = file.read()
        
        # Call the upload_blob function with the target language code
        result = upload_blob(file.filename, file_content, source_container_name, target_language_code)
        if "successfully" not in result: # Check if upload failed
            log("ERROR", f"Failed to upload source file '{file.filename}': {result}", user_name=user_name, data={"file": file.filename, "container": source_container_name})
            flush()
            return jsonify({"message": f"Error uploading source document: {result}"}), 500
        results.append(result)

    # Handle glossary file uploads
    glossary_file_extension = None # Initialize to None
    if glossary_files:
        for glossary_file in glossary_files:
            glossary_content = glossary_file.read()
            result = upload_blob2("glossary.csv", glossary_content, glossary_container_name) # Assuming fixed glossary filename
            if "successfully" not in result: # Check if upload failed
                log("ERROR", f"Failed to upload glossary file '{glossary_file.filename}': {result}", user_name=user_name, data={"file": glossary_file.filename, "container": glossary_container_name})
                flush()
                return jsonify({"message": f"Error uploading glossary file: {result}"}), 500
            results.append(result)

        # Detect the glossary format based on file extension
        glossary_file_extension = "csv"  # Default to CSV
        if glossary_files[0].filename.endswith('.tsv'):
            glossary_file_extension = "tsv"
        elif glossary_files[0].filename.endswith('.csv'):
            glossary_file_extension = "csv"
        log("INFO", f"Glossary file detected with format: {glossary_file_extension}", user_name=user_name)


    base_path_request = f"{document_translation_endpoint}translator/document/batches" # Renamed to avoid conflict with global base_path
    route = '?api-version=2024-05-01'
    constructed_url = base_path_request + route

    # Prepare payload
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

    if glossary_files and glossary_file_extension: # Add glossary only if files were present and format detected
        payload["inputs"][0]["targets"][0]["glossaries"] = [
            {
                "glossaryUrl": f"https://{account_name}.blob.core.windows.net/{glossary_container_name}/glossary.csv",
                "format": glossary_file_extension
            }
        ]
        log("INFO", "Payload includes glossary for translation.", user_name=user_name, data={"glossary_url": payload["inputs"][0]["targets"][0]["glossaries"][0]["glossaryUrl"]})
    else:
        log("INFO", "No glossary provided for translation.", user_name=user_name)

    headers = {
        'Ocp-Apim-Subscription-Key': api_key,
        'Content-Type': 'application/json'
    }

    job_id = None
    try:
        log("INFO", "Sending translation request to Azure Document Translation API.", user_name=user_name, data={"target_url": constructed_url})
        response = requests.post(constructed_url, headers=headers, json=payload)
        response.raise_for_status()
        job_id = response.json().get('id')  # Get the job ID from the response
        log("INFO", f"Translation job initiated successfully. Job ID: {job_id}", user_name=user_name, data={"job_id": job_id, "source_container": source_container_name, "target_container": target_container_name})
    except requests.exceptions.RequestException as e:
        log("ERROR", f"Request to Translator API failed: {str(e)}", user_name=user_name, data={"error_details": str(e), "api_url": constructed_url, "payload_snippet": json.dumps(payload)[:200]})
        flush()
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500
    except Exception as e:
        log("CRITICAL", f"An unexpected error occurred while initiating translation job: {e}", user_name=user_name, data={"error_type": type(e).__name__, "error_details": str(e)})
        flush()
        return jsonify({
            'status': 'error',
            'message': 'An internal server error occurred while initiating translation.'
        }), 500

    # Polling for the translation job status
    polling_interval = 5  # Increased polling interval to 5 seconds
    timeout = 900  # Timeout after 15 minutes (increased from 10 minutes)
    elapsed_time = 0
    sas_urls = {} # Initialize sas_urls

    log("INFO", f"Starting to poll for translation job status for Job ID: {job_id}", user_name=user_name)
    while elapsed_time < timeout:
        time.sleep(polling_interval)
        elapsed_time += polling_interval
        try:
            status_response = check_translation_status(job_id)
            if not status_response: # check_translation_status might return None on error
                log("ERROR", f"Failed to get status for job ID '{job_id}'. Aborting polling.", user_name=user_name)
                return jsonify({'status': 'error', 'message': 'Failed to retrieve translation job status.'}), 500

            current_status = status_response.get('status')
            log("DEBUG", f"Job ID '{job_id}' current status: {current_status}. Elapsed time: {elapsed_time}s", user_name=user_name)

            if current_status == 'Succeeded':
                log("INFO", f"Translation job '{job_id}' succeeded.", user_name=user_name)
                # Call get_blob_sas_urls immediately upon success
                sas_urls = get_blob_sas_urls(account_name, account_key, target_container_name)
                log("INFO", f"Generated SAS URLs for translated documents. Count: {len(sas_urls)}", user_name=user_name)
                break
            elif current_status in ['Failed', 'Cancelled']:
                log("ERROR", f"Translation job '{job_id}' failed or was cancelled. Details: {status_response}", user_name=user_name, data={"job_id": job_id, "status_details": status_response})
                flush()
                return jsonify({
                    'status': 'error',
                    'message': 'Translation job failed or was cancelled.',
                    'job_details': status_response
                }), 500
            elif elapsed_time >= timeout:
                log("WARNING", f"Translation job '{job_id}' timed out after {timeout} seconds. Current status: {current_status}", user_name=user_name, data={"job_id": job_id, "current_status": current_status})
                flush()
                return jsonify({
                    'status': 'error',
                    'message': 'Translation job timed out.',
                    'job_details': status_response
                }), 500
            # If not succeeded, failed, cancelled, or timed out, continue polling
            else:
                log("INFO", f"Translation job '{job_id}' still in progress. Current status: {current_status}.", user_name=user_name)
                pass # Continue loop
        except requests.exceptions.RequestException as e:
            log("ERROR", f"Error checking translation status for job ID '{job_id}': {str(e)}", user_name=user_name, data={"job_id": job_id, "error_details": str(e)})
            flush()
            return jsonify({
                'status': 'error',
                'message': f'Error checking translation status: {str(e)}'
            }), 500
        except Exception as e:
            log("CRITICAL", f"An unexpected error occurred during status polling for job ID '{job_id}': {e}", user_name=user_name, data={"job_id": job_id, "error_type": type(e).__name__, "error_details": str(e)})
            flush()
            return jsonify({
                'status': 'error',
                'message': 'An internal server error occurred during status polling.'
            }), 500

    # If job is succeeded, no need for additional waits
    if not sas_urls:
        log("ERROR", f"Translation job '{job_id}' completed but no SAS URLs were generated or retrieved.", user_name=user_name)
        return jsonify({
            'status': 'error',
            'message': 'Translation finished but failed to retrieve translated document URLs.'
        }), 500

    log("INFO", f"Document translation process completed successfully for job ID: {job_id}", user_name=user_name)
    flush()

    return jsonify({
        'status_code': response.status_code,
        'status': response.reason if response.status_code == 200 else "Succeeded", # Ensure status is "Succeeded" here
        'headers': dict(response.headers),
        'content': response.json(), # Initial response content
        'job_id': job_id, # Include job_id in final response
        'sas_urls': sas_urls,
        'source_container_name': source_container_name,
        'target_container_name': target_container_name,
        'glossary_container_name': glossary_container_name
    }), 200

if __name__ == '__main__':
    log("INFO", "Starting document translation server.", user_name=None)
    # In a production environment, debug=True should be removed for security.
    app.run(debug=True)
    log("INFO", "Document translation server shutting down.", user_name=None)
    flush()
