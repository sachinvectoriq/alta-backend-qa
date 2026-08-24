from flask import Flask, request, jsonify
import requests
import time
from datetime import datetime, timedelta
from azure.storage.blob import BlobServiceClient, generate_blob_sas, BlobSasPermissions
import os
from logging_config import log, flush  # Essential for logging

app = Flask(__name__)
# Log application startup
log("INFO", "Starting DeepL multiple file translation server.")
flush()

# Language mapping as provided (remains unchanged, not part of logging)
language_mapping = {
    "Arabic": "AR", "Bulgarian": "BG", "Czech": "CS", "Danish": "DA", "German": "DE",
    "Greek": "EL", "English": "EN", "English (British)": "EN-GB", "English (American)": "EN-US",
    "Spanish": "ES", "Estonian": "ET", "Finnish": "FI", "French": "FR", "Hungarian": "HU",
    "Indonesian": "ID", "Italian": "IT", "Japanese": "JA", "Korean": "KO", "Lithuanian": "LT",
    "Latvian": "LV", "Norwegian Bokmål": "NB", "Dutch": "NL", "Polish": "PL",
    "Portuguese": "PT", "Portuguese (Brazilian)": "PT-BR", "Portuguese (European)": "PT-PT",
    "Romanian": "RO", "Russian": "RU", "Slovak": "SK", "Slovenian": "SL", "Swedish": "SV",
    "Turkish": "TR", "Ukrainian": "UK", "Chinese": "ZH", "Chinese (Simplified)": "ZH-HANS",
    "Chinese (Traditional)": "ZH-HANT"
}

# Supported languages for formality (remains unchanged, not part of logging)
formality_supported_languages = {"DE", "FR", "IT", "ES", "NL", "PL", "PT-BR", "PT-PT", "JA", "RU"}

# Retrieve API keys and connection strings from environment variables
DEEPL_API_URL = os.getenv('DEEPL_API_URL')
DEEPL_API_KEY = os.getenv('DEEPL_API_KEY')
STORAGE_CONNECTION_STRING = os.getenv('STORAGE_CONNECTION_STRING')
STORAGE_SERVICE_ACCOUNT_NAME = os.getenv('STORAGE_SERVICE_ACCOUNT_NAME')
STORAGE_SERVICE_KEY = os.getenv('STORAGE_SERVICE_KEY')

# Initialize Azure Blob Service Client
# Log BlobServiceClient initialization status
try:
    blob_service_client = BlobServiceClient.from_connection_string(STORAGE_CONNECTION_STRING)
    log("INFO", "Azure BlobServiceClient initialized successfully.")
    flush()
except Exception as e:
    log("CRITICAL", f"Failed to initialize Azure BlobServiceClient: {e}",
        data={"connection_string_present": bool(STORAGE_CONNECTION_STRING)})
    flush()
    # Depending on your app's robustness, you might want to exit here or handle more gracefully


@app.route('/multiple_files2', methods=['POST'])
def multiple_files2():
    """
    Handles multiple document translation requests using DeepL API and Azure Blob Storage.
    """
    user_name = request.args.get('user_name')  # Get user_name for logging context
    # Log API request reception
    log("INFO", "Received POST request for /multiple_files2.", user_name=user_name)
    flush()

    try:
        # Retrieve form data
        files = request.files.getlist('file')
        source_lang = request.form.get('source_lang', 'auto')
        target_lang = request.form.get('target_lang')  # Changed to .get for safer access
        formality = request.form.get('formality')  # Changed to .get for safer access
        glossary_file = request.files.get('glossary_file')

        # Log received request parameters
        log("INFO",
            f"Request parameters: Source Lang='{source_lang}', Target Lang='{target_lang}', Formality='{formality}', Files Count={len(files)}, Glossary Present={bool(glossary_file)}",
            user_name=user_name)
        flush()

        source_lang_code = language_mapping.get(source_lang, 'auto')
        target_lang_code = language_mapping.get(target_lang)

        glossary_id = None
        if glossary_file:
            # Log glossary upload initiation
            log("INFO", f"Glossary file '{glossary_file.filename}' provided. Attempting to upload glossary.",
                user_name=user_name)
            flush()
            try:
                from create_glossary_deepl2 import upload_glossary
                response_gl = upload_glossary(source_lang, target_lang, glossary_file)  # Renamed to avoid conflict
                gl_data = response_gl
                glossary_id = gl_data["glossary_id"]
                # Log successful glossary upload
                log("INFO", f"Glossary uploaded successfully. Glossary ID: {glossary_id}", user_name=user_name)
                flush()
            except Exception as e:
                # Log glossary upload failure
                log("ERROR", f"Failed to upload glossary file '{glossary_file.filename}': {e}", user_name=user_name)
                flush()
                return jsonify({"error": f"Failed to upload glossary: {e}"}), 500

        if not target_lang_code:
            # Log invalid target language
            log("WARNING", f"Invalid target language provided: '{target_lang}'.", user_name=user_name)
            flush()
            return jsonify({"error": "Invalid target language"}), 400

        if target_lang_code not in formality_supported_languages and formality in ['more', 'less']:
            # Log formality not supported for target language
            log("WARNING", f"Formality '{formality}' not supported for target language '{target_lang_code}'.",
                user_name=user_name)
            flush()
            return jsonify({
                "error": f"Formality '{formality}' is not supported for the target language '{target_lang}'."
            }), 400

        # List to hold SAS URLs for all translated files
        sas_urls = []

        for file in files:
            # Log processing for each file
            log("INFO", f"Processing file '{file.filename}' for translation.", user_name=user_name)
            flush()
            # Prepare file and payload for the DeepL API request
            file_payload = {
                'file': (file.filename, file.stream, file.content_type),
                'target_lang': (None, target_lang_code),
                'source_lang': (None, source_lang_code if source_lang_code != 'auto' else None),
                'formality': (None, formality)
            }

            if glossary_id:  # Use glossary_id if it was successfully created
                file_payload['glossary_id'] = (None, glossary_id)

            headers = {
                'Authorization': f'DeepL-Auth-Key {DEEPL_API_KEY}'
            }

            # 1. Upload document for translation
            # Log DeepL API upload attempt
            log("INFO", f"Uploading '{file.filename}' to DeepL for translation.", user_name=user_name)
            flush()
            response = requests.post(DEEPL_API_URL, files=file_payload, headers=headers)

            if response.status_code != 200:
                # Log DeepL upload failure
                log("ERROR",
                    f"DeepL file upload failed for '{file.filename}'. Status: {response.status_code}, Response: {response.text}",
                    user_name=user_name)
                flush()
                return jsonify({"error": f"File upload failed for {file.filename}",
                                "details": response.text}), response.status_code

            response_data = response.json()
            document_id = response_data['document_id']
            document_key = response_data['document_key']
            # Log successful DeepL upload with IDs
            log("INFO", f"File '{file.filename}' uploaded to DeepL. Document ID: {document_id}", user_name=user_name)
            flush()

            # 2. Check translation status (polling)
            check_status_url = f"{DEEPL_API_URL}/{document_id}"
            status_payload = {"document_key": document_key}

            max_retries = 20
            retry_count = 0
            status = 'translating'
            retry_interval = 10  # Start with 10 seconds

            # Log polling start
            log("INFO", f"Starting polling for DeepL translation status of document ID {document_id}.",
                user_name=user_name)
            flush()
            while status in ['translating', 'queued'] and retry_count < max_retries:
                time.sleep(retry_interval)
                status_response = requests.post(check_status_url, json=status_payload, headers=headers)
                status_data = status_response.json()
                status = status_data['status']
                # Log current polling status
                log("INFO", f"Document ID {document_id} status: {status}. Retry count: {retry_count}",
                    user_name=user_name)
                flush()

                if status == 'done':
                    # Log successful translation status
                    log("INFO", f"Document ID {document_id} translation completed successfully.", user_name=user_name)
                    flush()
                    break
                elif status == 'failed':
                    error_message = status_data.get('error', 'Unknown error occurred')
                    # Log failed translation status
                    log("ERROR",
                        f"Translation failed for document ID {document_id}: {error_message}. Status details: {status_data}",
                        user_name=user_name)
                    flush()
                    return jsonify({
                        "error": f"Translation failed for {file.filename}",
                        "status_details": status_data,
                        "error_message": error_message
                    }), 500

                # Exponential backoff
                retry_interval = min(retry_interval * 2, 300)  # Cap at 5 minutes
                retry_count += 1

            if status != 'done':
                # Log timeout or max retries reached
                log("ERROR",
                    f"Translation for document ID {document_id} timed out or reached max retries. Current status: {status}",
                    user_name=user_name)
                flush()
                return jsonify({
                    "error": f"Translation still in progress for {file.filename} after maximum retries.",
                    "status_details": status_data
                }), 500

            # 3. Download the translated document
            # Log download attempt
            log("INFO", f"Attempting to download translated document for ID {document_id}.", user_name=user_name)
            flush()
            download_response = requests.post(f"{DEEPL_API_URL}/{document_id}/result",
                                              json={"document_key": document_key},
                                              headers=headers)

            if download_response.status_code != 200:
                # Log download failure
                log("ERROR",
                    f"Failed to download translated file for '{file.filename}'. Status: {download_response.status_code}, Response: {download_response.text}",
                    user_name=user_name)
                flush()
                return jsonify(
                    {"error": f"Failed to download translated file for {file.filename}"}), download_response.status_code

            # Create translated blob name
            translated_blob_name = f"{file.filename.rsplit('.', 1)[0]}-{target_lang_code}.{file.filename.rsplit('.', 1)[-1]}"

            # Generate unique container name for each translation job (or per file if multiple files)
            container_name = f"destination-{datetime.now().strftime('%Y%m%d%H%M%S')}"

            # Log container creation attempt
            log("INFO", f"Creating container '{container_name}' for translated file '{translated_blob_name}'.",
                user_name=user_name)
            flush()
            try:
                blob_service_client.create_container(container_name)
                log("INFO", f"Container '{container_name}' created successfully.", user_name=user_name)
                flush()
            except Exception as e:
                log("ERROR", f"Failed to create container '{container_name}': {e}", user_name=user_name)
                flush()
                return jsonify({"error": f"Failed to create storage container: {e}"}), 500

            # Upload the translated document to Azure Blob Storage
            blob_client = blob_service_client.get_blob_client(container=container_name, blob=translated_blob_name)

            # Log upload to Azure Blob
            log("INFO", f"Uploading translated file '{translated_blob_name}' to Azure Blob Storage.",
                user_name=user_name)
            flush()
            blob_client.upload_blob(download_response.content, overwrite=True)
            log("INFO", f"Translated file '{translated_blob_name}' uploaded successfully to Azure Blob.",
                user_name=user_name)
            flush()

            # Generate a SAS URL for the uploaded blob
            # Log SAS URL generation attempt
            log("INFO", f"Generating SAS URL for '{translated_blob_name}' in container '{container_name}'.",
                user_name=user_name)
            flush()
            sas_token = generate_blob_sas(
                account_name=os.getenv('STORAGE_SERVICE_ACCOUNT_NAME'),
                account_key=os.getenv('STORAGE_SERVICE_KEY'),
                container_name=container_name,
                blob_name=translated_blob_name,
                permission=BlobSasPermissions(read=True),
                expiry=datetime.utcnow() + timedelta(hours=1)
            )

            sas_url = f"https://{blob_service_client.account_name}.blob.core.windows.net/{container_name}/{translated_blob_name}?{sas_token}"
            sas_urls.append({"file_name": translated_blob_name, "sas_url": sas_url})
            # Log successful SAS URL generation
            log("INFO", f"SAS URL generated for '{translated_blob_name}'.", user_name=user_name)
            flush()

        # Log successful completion of all file translations
        log("INFO", "All files translated and SAS URLs generated successfully.", user_name=user_name)
        flush()
        return jsonify({"sas_urls": sas_urls})

    except requests.exceptions.RequestException as e:
        # Log network/API request errors
        log("ERROR", f"DeepL API request error: {e}", user_name=user_name)
        flush()
        return jsonify({"error": f"DeepL API request failed: {str(e)}"}), 500
    except Exception as e:
        # Log unhandled exceptions
        log("CRITICAL", f"An unexpected error occurred during /multiple_files2 request: {e}", user_name=user_name)
        flush()
        return jsonify({"error": str(e)}), 500


if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    # Log Flask application startup details
    log("INFO", f"Flask application is starting up on port {port}.", data={"host": "0.0.0.0", "port": port})
    try:
        app.run(host="0.0.0.0", port=port, debug=True)
    except Exception as e:
        # Log critical error if app fails to start
        log("CRITICAL", f"Flask application failed to start: {e}", data={"error_details": str(e)})
        flush()
    finally:
        # Log application shutdown
        log("INFO", "Flask application is shutting down. Flushing remaining logs.")
        flush()
