from flask import Flask, request, jsonify, Response
import requests
import time
from datetime import datetime, timedelta
from azure.storage.blob import BlobServiceClient, generate_blob_sas, BlobSasPermissions
import os
import csv
import io

app = Flask(__name__)

# Language mapping as provided
language_mapping = {
    "Arabic": "AR",
    "Bulgarian": "BG",
    "Czech": "CS",
    "Danish": "DA",
    "German": "DE",
    "Greek": "EL",
    "English": "EN",
    "English (British)": "EN-GB",
    "English (American)": "EN-US",
    "Spanish": "ES",
    "Estonian": "ET",
    "Finnish": "FI",
    "French": "FR",
    "Hungarian": "HU",
    "Indonesian": "ID",
    "Italian": "IT",
    "Japanese": "JA",
    "Korean": "KO",
    "Lithuanian": "LT",
    "Latvian": "LV",
    "Norwegian Bokmål": "NB",
    "Dutch": "NL",
    "Polish": "PL",
    "Portuguese": "PT",
    "Portuguese (Brazilian)": "PT-BR",
    "Portuguese (European)": "PT-PT",
    "Romanian": "RO",
    "Russian": "RU",
    "Slovak": "SK",
    "Slovenian": "SL",
    "Swedish": "SV",
    "Turkish": "TR",
    "Ukrainian": "UK",
    "Chinese": "ZH",
    "Chinese (Simplified)": "ZH-HANS",
    "Chinese (Traditional)": "ZH-HANT"
}

# Supported languages for formality
formality_supported_languages = {"DE", "FR", "IT", "ES", "NL", "PL", "PT-BR", "PT-PT", "JA", "RU"}

# DEEPL_API_URL = 'https://api.deepl.com/v2/document'
# DEEPL_API_KEY = '82a64fae-73d4-4739-9935-bbf3cfc15010'  # Replace with your actual DeepL API key



DEEPL_API_URL = "https://api.deepl.com/v2/document"
DEEPL_API_KEY = "82a64fae-73d4-4739-9935-bbf3cfc15010"  # Replace with your actual DeepL API key
# STORAGE_CONNECTION_STRING = "DefaultEndpointsProtocol=https;AccountName=prodaitranslationstorage;AccountKey=nUJ0M5ErCZMRNdD6HvDgT1xYzqr32u7TMTTShfm+62qRIOdoasPBbIkjJjhIdJwLr2hslUtxYJaE+AStqJEvLw==;EndpointSuffix=core.windows.net"
STORAGE_CONNECTION_STRING = "DefaultEndpointsProtocol=https;AccountName=devaitranslationstorage;AccountKey=GtiG/Hm1kzpGy8aElsdqgBiApPvUgEg+8DbylzCUYV+f4ZCfsNFRCLLIsfrvPemzXqm5hnIw6VGA+AStpe8FWQ==;EndpointSuffix=core.windows.net"



# Initialize Azure Blob Service Client
blob_service_client = BlobServiceClient.from_connection_string(STORAGE_CONNECTION_STRING)









@app.route('/multiple_files3', methods=['POST'])
def multiple_files3():
    try:
        # Retrieve form data
        files = request.files.getlist('file')
        source_lang = request.form.get('source_lang', 'auto')
        target_lang = request.form['target_lang']
        formality = request.form['formality']
        glossary_file = request.files.get('glossary_file')

        source_lang_code = language_mapping.get(source_lang, 'auto')
        target_lang_code = language_mapping.get(target_lang)

        glossary_id = None
        if glossary_file:
            try:
                # Read the original content
                file_content = glossary_file.read().decode('utf-8')
                is_csv = not glossary_file.filename.lower().endswith('.tsv')
                delimiter = ',' if is_csv else '\t'

                # Clean the content
                rows = list(csv.reader(io.StringIO(file_content), delimiter=delimiter))
                cleaned_rows = []
                whitespace_issues = []

                # Check and clean leading/trailing whitespaces
                for row_idx, row in enumerate(rows):
                    cleaned_row = []
                    for col_idx, cell in enumerate(row):
                        cleaned_cell = cell.strip()
                        cleaned_row.append(cleaned_cell)
                    cleaned_rows.append(cleaned_row)

                # Convert back to string
                output = io.StringIO()
                writer = csv.writer(output, delimiter=delimiter)
                writer.writerows(cleaned_rows)
                cleaned_content = output.getvalue()

                # Create a file-like object from the cleaned content
                cleaned_file = io.BytesIO(cleaned_content.encode('utf-8'))
                cleaned_file.filename = glossary_file.filename  # Add filename attribute
                cleaned_file.content_type = 'text/csv' if is_csv else 'text/tab-separated-values'

                # Import and use upload_glossary with cleaned file
                from create_glossary_deepl2 import upload_glossary
                response = upload_glossary(source_lang, target_lang, cleaned_file)
                if "error" in response:
                    return jsonify({
                        "error": response.get("error"),
                        "status_code": response.get("status_code", 500)
                    }), response.get("status_code", 500)
                print('Response from Upload Glossary:', response)
                glossary_id = response["glossary_id"]

            except Exception as e:
                print(f"Glossary processing error: {str(e)}")
                return jsonify({"error": f"Error processing glossary file: {str(e)}"}), 400

        if not target_lang_code:
            return jsonify({"error": "Invalid target language"}), 400

        if target_lang_code not in formality_supported_languages and formality in ['more', 'less']:
            return jsonify({
                "error": f"Formality '{formality}' is not supported for the target language '{target_lang}'."
            }), 400

        # List to hold document info for all files
        documents_info = []

        for file in files:
            # Generate the new file name with the target language code
            original_filename = file.filename
            file_extension = os.path.splitext(original_filename)[1]
            new_filename = f"{os.path.splitext(original_filename)[0]}-{target_lang_code}{file_extension}"

            # Prepare file and payload for the DeepL API request
            file_payload = {
                'file': (new_filename, file.stream, file.content_type),
                'target_lang': (None, target_lang_code),
                'source_lang': (None, source_lang_code if source_lang_code != 'auto' else None),
                'formality': (None, formality)
            }

            if glossary_id:
                file_payload['glossary_id'] = (None, glossary_id)

            headers = {
                'Authorization': f'DeepL-Auth-Key {DEEPL_API_KEY}'
            }

            # Upload document for translation
            response = requests.post(DEEPL_API_URL, files=file_payload, headers=headers)

            if response.status_code != 200:
                return jsonify({"error": f"File upload failed for {file.filename}"}), response.status_code

            response_data = response.json()
            document_id = response_data['document_id']
            document_key = response_data['document_key']
            
            translated_blob_name = f"{file.filename.rsplit('.', 1)[0]}-{target_lang_code}.{file.filename.rsplit('.', 1)[-1]}"
            
            documents_info.append({
                "document_id": document_id,
                "document_key": document_key,
                "file_name": translated_blob_name,
            })

        return jsonify({"documents": documents_info}), 200

    except Exception as e:
        print(f"General error: {str(e)}")
        return jsonify({"error": str(e)}), 500
