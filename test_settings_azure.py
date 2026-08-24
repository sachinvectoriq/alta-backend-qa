# test_settings_azure.py

import requests
from flask import request, jsonify
from azure.storage.blob import BlobServiceClient
import traceback  # Import traceback for detailed error logging

# Import log and flush from your logging_config
from logging_config import log, flush

# Hardcoded source document URL, source language, and target language
# Consider making these configurable via environment variables or a settings table
SOURCE_DOCUMENT_URL = "https://devaitranslationstorage.blob.core.windows.net/source/Body%20is%20the%20temple.docx?sp=r&st=2024-10-10T13:21:05Z&se=2026-02-25T21:21:05Z&spr=https&sv=2022-11-02&sr=b&sig=TUldqtSd0ljLMMOzrMnrot0FzBI7r0uwz%2BnDKkpntRc%3D"
TARGET_DOCUMENT_URL = "https://devaitranslationstorage.blob.core.windows.net/translated/translated_doc_es.docx"
SOURCE_LANGUAGE_CODE = "en"  # English as source language
TARGET_LANGUAGE_CODE = "es"  # Spanish as target language


def test_translation():
    log('INFO', 'Received request to test Azure Text Translation.')
    # Get the inputs from form-data or query parameters
    key = request.form.get('key')  # Azure Translator API key
    text_translation_endpoint = request.form.get('endpoint')  # Translator service endpoint URL
    region = request.form.get('region')  # Azure region

    # Hardcoded values for translation
    source_language_code = "en"  # English as source language
    target_language_code = "es"  # Spanish as target language
    text_to_translate = "This is a test"  # Text to translate

    # Check if key, endpoint, and region are provided
    if not key or not text_translation_endpoint or not region:
        log('WARNING', 'Missing required parameters for text translation test.',
            data={'key_provided': bool(key), 'endpoint_provided': bool(text_translation_endpoint),
                  'region_provided': bool(region)})
        flush()
        return jsonify({"error": "API key, endpoint, and region are required."}), 400

    log('INFO', 'All required parameters for text translation test are present.')

    # Construct the Azure Translator API URL
    path = 'translate'
    constructed_url = f"{text_translation_endpoint}/{path}"

    # Setup the query parameters and headers
    params = {
        'api-version': '3.0',
        'from': source_language_code,
        'to': target_language_code
    }

    headers = {
        'Ocp-Apim-Subscription-Key': key,
        'Ocp-Apim-Subscription-Region': region,
        'Content-Type': 'application/json'
    }

    # Body of the request with the hardcoded text to be translated
    body = [{'text': text_to_translate}]

    try:
        log('INFO', 'Making request to Azure Text Translator API.',
            data={'url': constructed_url, 'from': source_language_code, 'to': target_language_code})
        # Make the request to the Azure Translator API
        response = requests.post(constructed_url, params=params, headers=headers, json=body)
        response.raise_for_status()  # Raises an HTTPError for bad responses

        # Parse the response JSON
        response_json = response.json()
        log('INFO', 'Azure Text Translator API call successful.',
            data={'status_code': response.status_code, 'response_preview': str(response_json)[:200]})  # Log a preview
        flush()
        # Return the JSON response from the API
        return jsonify(response_json), 200

    except requests.exceptions.HTTPError as http_err:
        # Catch HTTP errors from the API call
        error_traceback = traceback.format_exc()
        log('ERROR', f"HTTP error occurred during text translation: {http_err}",
            data={'status_code': http_err.response.status_code if http_err.response else 'N/A',
                  'response_text': http_err.response.text if http_err.response else 'N/A',
                  'traceback': error_traceback})
        flush()
        return jsonify({"error": f"HTTP error occurred: {http_err}"}), 500
    except Exception as e:
        # Catch any other errors
        error_traceback = traceback.format_exc()
        log('CRITICAL', f"An unexpected error occurred during text translation: {e}",
            data={'traceback': error_traceback})
        flush()
        return jsonify({"error": f"An unexpected error occurred: {str(e)}"}), 500


def translate_document():
    log('INFO', 'Received request to test Azure Document Translation.')
    # Get key, endpoint, and region from request
    key = request.form.get('key')
    text_translation_endpoint = request.form.get(
        'endpoint')  # This should probably be document_translation_endpoint based on context
    region = request.form.get('region')

    # Validate key, endpoint, and region
    if not key or not text_translation_endpoint or not region:
        log('WARNING', 'Missing required parameters for document translation test.',
            data={'key_provided': bool(key), 'endpoint_provided': bool(text_translation_endpoint),
                  'region_provided': bool(region)})
        flush()
        return jsonify({"error": "API key, endpoint, and region are required."}), 400

    log('INFO', 'All required parameters for document translation test are present.')

    # Construct the Azure Document Translation API URL
    # Assuming text_translation_endpoint is actually the document translation endpoint here based on its usage below
    constructed_url = f"{text_translation_endpoint}/translator/text/batch/v1.0/batches"

    # Setup the request body and headers with hardcoded URLs and languages
    body = {
        "inputs": [
            {
                "source": {
                    "sourceUrl": SOURCE_DOCUMENT_URL,
                    "language": SOURCE_LANGUAGE_CODE
                },
                "targets": [
                    {
                        "targetUrl": TARGET_DOCUMENT_URL,
                        "language": TARGET_LANGUAGE_CODE
                    }
                ]
            }
        ]
    }

    headers = {
        'Ocp-Apim-Subscription-Key': key,
        'Ocp-Apim-Subscription-Region': region,
        'Content-Type': 'application/json'
    }

    try:
        log('INFO', 'Making request to Azure Document Translation API.',
            data={'url': constructed_url, 'source_doc_url': SOURCE_DOCUMENT_URL, 'target_doc_url': TARGET_DOCUMENT_URL})
        # Make the request to the Azure Document Translation API
        response = requests.post(constructed_url, headers=headers, json=body)

        # Log the status code and response text
        log('INFO', f"Document Translation API Response - Status Code: {response.status_code}",
            data={'response_text_preview': response.text[:200]})

        # Raise an error for bad responses
        response.raise_for_status()

        # If the request is successful, return success message
        log('INFO', "Document translation request sent successfully to Azure.")
        flush()
        return jsonify({"success": True, "message": "Document translation started successfully."}), 200

    except requests.exceptions.HTTPError as http_err:
        error_traceback = traceback.format_exc()
        log('ERROR', f"HTTP error occurred during document translation: {http_err}",
            data={'status_code': http_err.response.status_code if http_err.response else 'N/A',
                  'response_text': http_err.response.text if http_err.response else 'N/A',
                  'traceback': error_traceback})
        flush()
        return jsonify({"error": f"HTTP error occurred: {http_err}"}), 500
    except Exception as e:
        error_traceback = traceback.format_exc()
        log('CRITICAL', f"An unexpected error occurred during document translation: {e}",
            data={'traceback': error_traceback})
        flush()
        return jsonify({"error": f"An unexpected error occurred: {str(e)}"}), 500


def validate_connection_string(connection_string):
    log('INFO', 'Attempting to validate Azure Blob Storage connection string.')
    try:
        # Attempt to create BlobServiceClient with the provided connection string
        blob_service_client = BlobServiceClient.from_connection_string(connection_string)
        # Try to list containers to validate the connection
        # This operation confirms if the connection string provides access
        log('INFO', 'Attempting to list containers to validate Azure Blob Storage connection.')
        containers = blob_service_client.list_containers()
        for container in containers:
            # Just iterating to ensure access, no need to log container names here usually
            pass
        log('INFO', 'Azure Blob Storage connection string validated successfully.')
        return True
    except Exception as e:
        error_traceback = traceback.format_exc()
        log('ERROR', f"Connection string validation failed: {e}",
            data={'error_details': str(e), 'traceback': error_traceback})
        return False


def validate_connection_string_route():
    log('INFO', 'Received request to validate Azure Blob Storage connection string via route.')
    # Extract connection string from request
    connection_string = request.form.get('connection_string')

    # Ensure connection string is provided
    if not connection_string:
        log('WARNING', 'Connection string is missing for validation route.')
        flush()
        return jsonify({"error": "Connection string is required."}), 400

    # Validate the connection string using the function
    if validate_connection_string(connection_string):
        log('INFO', 'Azure Blob Storage connection string is valid.')
        flush()
        return jsonify({"success": True, "message": "Valid Azure Blob Storage connection string."}), 200
    else:
        log('ERROR', 'Azure Blob Storage connection string is invalid.')
        flush()
        return jsonify({"error": "Invalid Azure Blob Storage connection string."}), 400


def run_all_operations():
    log('INFO',
        'Received request to run all Azure operations (Text, Document Translation, and Blob Storage validation).')
    # Get the inputs from form-data
    key = request.form.get('key')  # Azure Translator API key
    text_translation_endpoint = request.form.get('text_translation_endpoint')  # Text translation service endpoint URL
    document_translation_endpoint = request.form.get(
        'document_translation_endpoint')  # Document translation endpoint URL
    region = request.form.get('region')  # Azure region

    # Validate key, endpoints, and region
    if not key or not text_translation_endpoint or not document_translation_endpoint or not region:
        log('WARNING', 'Missing one or more required parameters for running all operations.',
            data={'key_provided': bool(key), 'text_endpoint_provided': bool(text_translation_endpoint),
                  'doc_endpoint_provided': bool(document_translation_endpoint), 'region_provided': bool(region)})
        flush()
        return jsonify({
            "error": "API key, text translation endpoint, document translation endpoint, and region are required."
        }), 400

    log('INFO', 'All required parameters for running all operations are present.')

    # Initialize results
    results = {}
    all_successful = True  # Flag to check if all operations are successful

    # Step 1: Test Text Translation
    log('INFO', 'Starting Text Translation test within run_all_operations.')
    try:
        source_language_code = "en"  # English as source language
        target_language_code = "es"  # Spanish as target language
        text_to_translate = "This is a test"

        # Construct the Azure Text Translator API URL
        constructed_url = f"{text_translation_endpoint}/translate"
        params = {'api-version': '3.0', 'from': source_language_code, 'to': target_language_code}
        headers = {
            'Ocp-Apim-Subscription-Key': key,
            'Ocp-Apim-Subscription-Region': region,
            'Content-Type': 'application/json'
        }
        body = [{'text': text_to_translate}]

        # Make the request to the Text Translation API
        translation_response = requests.post(constructed_url, params=params, headers=headers, json=body)
        translation_response.raise_for_status()  # Raise exception for bad status codes

        # Add text translation result to the results dictionary
        results['text_translation'] = translation_response.json()
        log('INFO', 'Text Translation test successful in run_all_operations.')
    except Exception as e:
        error_traceback = traceback.format_exc()
        results['text_translation'] = {"error": str(e), "traceback": error_traceback}
        all_successful = False  # Set flag to False if there was an error
        log('ERROR', f'Text Translation test failed in run_all_operations: {e}', data={'traceback': error_traceback})

    # Step 2: Test Document Translation
    log('INFO', 'Starting Document Translation test within run_all_operations.')
    try:
        # Construct the Azure Document Translation API URL
        document_translation_url = f"{document_translation_endpoint}/translator/text/batch/v1.0/batches"
        body = {
            "inputs": [
                {
                    "source": {"sourceUrl": SOURCE_DOCUMENT_URL, "language": SOURCE_LANGUAGE_CODE},
                    "targets": [{"targetUrl": TARGET_DOCUMENT_URL, "language": TARGET_LANGUAGE_CODE}]
                }
            ]
        }
        headers = {
            'Ocp-Apim-Subscription-Key': key,
            'Ocp-Apim-Subscription-Region': region,
            'Content-Type': 'application/json'
        }

        # Make the request to the Document Translation API
        document_response = requests.post(document_translation_url, headers=headers, json=body)
        document_response.raise_for_status()  # Raise exception for bad status codes

        # Add document translation result to the results dictionary
        results['document_translation'] = {"message": "Document translation started successfully."}
        log('INFO', 'Document Translation test successful in run_all_operations.')
    except Exception as e:
        error_traceback = traceback.format_exc()
        results['document_translation'] = {"error": str(e), "traceback": error_traceback}
        all_successful = False  # Set flag to False if there was an error
        log('ERROR', f'Document Translation test failed in run_all_operations: {e}',
            data={'traceback': error_traceback})

    # Determine the status code based on the success of operations
    if all_successful:
        log('INFO', 'All Azure operations completed successfully.')
        flush()
        return jsonify(results), 200
    else:
        log('ERROR', 'One or more Azure operations failed during run_all_operations.', data={'results': results})
        flush()
        return jsonify(results), 500  # Return 500 if any operation failed
