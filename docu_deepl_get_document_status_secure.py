
from flask import Flask, request, jsonify
import requests
import os
import psycopg2
# Import log and flush functions from the logging_config file
#from logging_config import log, flush

app = Flask(__name__)

DEEPL_BASE_URL = os.getenv('DEEPL_API_URL')

global storage_connection_string, deepl_api_key
deepl_api_key = None
storage_connection_string = None


def retrieve_settings():
    """
    Retrieves DeepL API key and Azure Storage connection string from the database.
    """
    global storage_connection_string, deepl_api_key
    user_name = request.args.get('user_name')  # Get user_name from query parameters

    #log("INFO", "Attempting to retrieve settings from the database for status check.", user_name=user_name)
    #flush()

    try:
        # Database connection
        connection = psycopg2.connect(
            database=os.getenv('DB_NAME'),
            user=os.getenv('DB_USER'),
            password=os.getenv('DB_PASSWORD'),
            host=os.getenv('DB_HOST'),
            port=os.getenv('DB_PORT')
        )
        cursor = connection.cursor()

        #log("INFO", "Connected to the database successfully for settings retrieval.", user_name=user_name)
        #flush()

        # Query to fetch storage_connection_string from the settings table
        query_settings = """
        SELECT storage_connection_string
        FROM settings
        WHERE admin_id = %s;
        """
        cursor.execute(query_settings, ('1',))
        result_settings = cursor.fetchone()

        if not result_settings:
            #log("ERROR", "No storage settings found for Admin_id 1 in the 'settings' table.", user_name=user_name)
            #flush()
            return None, None

        storage_connection_string = result_settings[0]
        #log("INFO", "Storage connection string retrieved.",data={"storage_connection_string_present": bool(storage_connection_string)}, user_name=user_name)
        #flush()

        # Query to fetch api_key from the deepl_settings table
        query_deepl_settings = """
        SELECT api_key
        FROM deepl_settings
        WHERE admin_id = %s;
        """
        cursor.execute(query_deepl_settings, ('1',))
        result_deepl_settings = cursor.fetchone()

        if not result_deepl_settings:
            #log("ERROR", "No DeepL API key settings found for Admin_id 1 in the 'deepl_settings' table.",user_name=user_name)
            #flush()
            return None, None

        deepl_api_key = result_deepl_settings[0]
        #log("INFO", "DeepL API key retrieved.", data={"deepl_api_key_present": bool(deepl_api_key)},user_name=user_name)
        #flush()

        cursor.close()
        connection.close()

        #log("INFO", "All settings retrieved successfully.", user_name=user_name)
        #flush()
        return deepl_api_key, storage_connection_string

    except psycopg2.Error as db_err:
        #log("ERROR", f"Database error during settings retrieval: {db_err}", user_name=user_name)
        #flush()
        return None, None
    except Exception as e:
        #log("ERROR", f"General error retrieving settings: {e}", user_name=user_name)
        #flush()
        return None, None


def validate_bearer_token(request, expected_token):
    """
    Validates the Bearer token from the Authorization header in the request.
    Returns an error response if invalid; otherwise, returns None.
    """
    user_name = request.args.get('user_name')  # Get user_name from query parameters
    auth_header = request.headers.get('Authorization', '')

    if not auth_header.startswith('Bearer '):
        #log("WARNING", "Invalid or missing Authorization header for token validation.", data={"auth_header_snippet": auth_header[:10]}, user_name=user_name)
        #flush()
        return jsonify({"error": "Invalid or missing Authorization header."}), 401

    token = auth_header.split(' ')[1]
    if token != expected_token:
        #log("ERROR", "Unauthorized access attempt with invalid Bearer token.",data={"provided_token_prefix": token[:5] + "...", "expected_token_prefix": expected_token[:5] + "..."},user_name=user_name)
        #flush()
        return jsonify({"error": "Unauthorized. Invalid Bearer token."}), 403

    #log("INFO", "Bearer token validated successfully.", user_name=user_name)
    #flush()
    return None  # No error


def check_status_secure():
    """
    Checks the translation status of documents with DeepL API.
    """
    user_name = request.args.get('user_name')  # Get user_name from query parameters
    #log("INFO", "Starting check_status_secure endpoint.", user_name=user_name)
    #flush()

    deepl_api_key, storage_connection_string = retrieve_settings()
    if not deepl_api_key or not storage_connection_string:
        #log("ERROR", "Failed to retrieve required settings for DeepL API or Azure Storage.", user_name=user_name)
        #flush()
        return jsonify({"error": "Failed to retrieve required settings"}), 500

    auth_error = validate_bearer_token(request, 'A7x!G2p@Q9#L')  # Replace 'A7x!G2p@Q9#L' with your actual token
    if auth_error:
        #log("WARNING", "Bearer token validation failed for status check.", user_name=user_name)
        #flush()
        return auth_error

    try:
        # Parse the JSON input
        input_data = request.json
        #log("INFO", "Received input data for status check.", data={"input_data_type": type(input_data).__name__,"input_data_len": len(input_data) if isinstance(input_data, list) else None},user_name=user_name)
        #flush()

        # Validate input data
        if not isinstance(input_data, list) or len(input_data) == 0:
            #log("WARNING", "Invalid input data format: Input should be a non-empty list.",
                #data={"received_input": input_data}, user_name=user_name)
            #flush()
            return jsonify(
                {'error': 'Input should be a list of dictionaries with file_name, document_id, and document_key'}), 400

        # Initialize an empty list for results
        results = []

        # Iterate over each input group
        for group in input_data:
            file_name = group.get('file_name')
            document_id = group.get('document_id')
            document_key = group.get('document_key')

            #log("INFO", f"Processing status check for document: {file_name}", data={"document_id": document_id},user_name=user_name)
            #flush()

            # Check for missing fields
            if not file_name or not document_id or not document_key:
                #log("WARNING", f"Missing document_id or document_key for file: {file_name or 'Unknown'}",data={"group_data": group}, user_name=user_name)
                #flush()
                results.append({
                    'file_name': file_name or 'Unknown',
                    'error': 'Missing document_id or document_key'
                })
                continue

            # Prepare the request URL and parameters
            url = f"{DEEPL_BASE_URL}/{document_id}"
            headers = {'Authorization': f"DeepL-Auth-Key {deepl_api_key}"}
            # DeepL API for document status uses GET with params, not POST with JSON body.
            # Correcting this based on typical DeepL document API behavior for status checks.
            params = {'document_key': document_key}

            # Send the request to DeepL API
            try:
                #log("INFO", f"Sending status request to DeepL API for document ID: {document_id}", user_name=user_name)
                #flush()
                response = requests.get(url, headers=headers, params=params)  # Changed to GET with params
                response.raise_for_status()  # Raise an exception for HTTP errors (4xx or 5xx)
                response_data = response.json()

                # # Process the response
                # if response.status_code == 200:



                if response.status_code == 200:
                    # single block: distinguish business‐logic error vs success
                    if response_data.get('status') == 'error':
                        '''log(
                            "ERROR",
                            f"DeepL returned status 'error' for document: {file_name}",
                            data={"message": response_data.get('message', 'No message')},
                            user_name=user_name
                        )
                        flush()
                        '''
                        results.append({
                            'file_name': file_name,
                            'document_id': document_id,
                            'document_key': document_key,
                            'status': 'error',
                            'error': response_data.get('message', 'No message')
                        })
                    else:
                        '''
                        log(
                            "INFO",
                            f"Successfully retrieved status for document: {file_name}",
                            data={"status": response_data.get('status')},
                            user_name=user_name
                        )
                        flush()
                        '''
                        results.append({
                            'file_name': file_name,
                            'document_id': document_id,
                            'document_key': document_key,
                            'status': response_data.get('status'),
                            'seconds_remaining': response_data.get('seconds_remaining'),
                            'billed_characters': response_data.get('billed_characters')
                        })

                else:
                    '''
                    # This block might be redundant if raise_for_status handles most errors, but kept for explicit non-200 DeepL responses.
                    log("ERROR",
                        f"DeepL API returned non-200 status for document '{file_name}': {response.status_code}",
                        data={"response_message": response_data.get('message', 'No message')}, user_name=user_name)
                    flush()
                    '''
                    results.append({
                        'file_name': file_name,
                        'error': response_data.get('message', 'Unknown error')
                    })
            except requests.exceptions.HTTPError as http_err:
                '''
                log("ERROR", f"HTTP error during DeepL status check for '{file_name}': {http_err}",
                    data={"status_code": response.status_code, "response_text": response.text}, user_name=user_name)
                flush()
                '''
                results.append({
                    'file_name': file_name,
                    'error': f"DeepL API HTTP error: {http_err}. Message: {response.json().get('message', 'No message')}"
                })
            except requests.exceptions.ConnectionError as conn_err:
                '''
                log("CRITICAL", f"Connection error to DeepL API for '{file_name}': {conn_err}", user_name=user_name)
                flush()
                '''
                results.append({
                    'file_name': file_name,
                    'error': f"Network connection error to DeepL API: {conn_err}"
                })
            except requests.exceptions.Timeout as timeout_err:
                '''
                log("WARNING", f"Timeout error with DeepL API for '{file_name}': {timeout_err}", user_name=user_name)
                flush()
                '''
                results.append({
                    'file_name': file_name,
                    'error': f"DeepL API request timed out: {timeout_err}"
                })
            except requests.exceptions.RequestException as req_err:
                '''
                log("ERROR", f"An unexpected request error occurred with DeepL API for '{file_name}': {req_err}",
                    user_name=user_name)
                flush()
                '''
                results.append({
                    'file_name': file_name,
                    'error': f"An unexpected request error: {req_err}"
                })
            except Exception as e:
                '''
                log("CRITICAL", f"Unhandled error during DeepL status check loop for '{file_name}': {str(e)}",
                    user_name=user_name)
                flush()
                '''
                results.append({
                    'file_name': file_name,
                    'error': f"Error checking status: {str(e)}"
                })

        # Return the aggregated results
        #log("INFO", "All document status checks completed. Returning aggregated results.", user_name=user_name)
        #flush()
        # ← Compute overall HTTP status *inside* the try, before returning:
        overall_code = 200
        for r in results:
            if r.get('status') == 'error':
                overall_code = 207   # partial failure
                break

        # ← Use that code here instead of always 200:
        return jsonify(results), overall_code

    except Exception as e:
        #log("CRITICAL", f"General unhandled error in check_status_secure: {str(e)}", user_name=user_name)
        #flush()
        return jsonify({'error': str(e)}), 500


if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    
