from datetime import datetime, timedelta
from azure.storage.blob import BlobServiceClient, generate_blob_sas, BlobSasPermissions
import requests
from flask import Flask, request, jsonify
import os
import re
import random

app = Flask(__name__)

# Constants
DEEPL_API_URL = os.getenv('DEEPL_DOCUMENT_TRANSLATION_URL')
DEEPL_API_KEY=os.getenv('DEEPL_API_KEY')
STORAGE_ACCOUNT_NAME = os.getenv('STORAGE_SERVICE_ACCOUNT_NAME')
sas_urls = []

# Replace with your Azure Storage connection string and account key
connection_string = os.getenv('STORAGE_CONNECTION_STRING')
account_key = os.getenv('STORAGE_SERVICE_KEY')

@app.route('/download_translate_upload', methods=['POST'])
def download_translate_upload():
    try:
        # Get document_id and document_key from form data
        document_id = request.form.get("document_id")
        document_key = request.form.get("document_key")
        translated_blob_name =request.form.get("file_name")

        if not document_id or not document_key:
            return jsonify({"error": "Both document_id and document_key are required."}), 400

        # 1. Download the translated document
        headers = {'Authorization': f'DeepL-Auth-Key {DEEPL_API_KEY}'}
        download_response = requests.post(
            f"{DEEPL_API_URL}/{document_id}/result",
            json={"document_key": document_key},
            headers=headers
        )

        if download_response.status_code != 200:
            return jsonify({"error": f"Failed to download translated file: {download_response.text}"}), download_response.status_code


        # Initialize BlobServiceClient
        blob_service_client = BlobServiceClient.from_connection_string(connection_string)

        # 3. Create a new container with a unique name
        container_name = os.getenv('DEEPL_CONTAINER')

        # 4. Upload the translated document to Azure Blob Storage
        blob_client = blob_service_client.get_blob_client(container=container_name, blob=translated_blob_name)

        # Check if the blob with the same name already exists
        if blob_client.exists():
            # Generate a random 3-digit number
            random_number = random.randint(100, 999)
            
            # Generate a new name for the blob
            translated_blob_name = f"{translated_blob_name.rsplit('.', 1)[0]}-{random_number}.{translated_blob_name.rsplit('.', 1)[-1]}"
            
            # Create a new BlobClient with the updated name
            blob_client = blob_service_client.get_blob_client(container=container_name, blob=translated_blob_name)
        
        # Upload the file to the container
        blob_client.upload_blob(download_response.content, overwrite=True)


        # 5. Generate a SAS URL for the uploaded blob
        sas_token = generate_blob_sas(
            account_name=STORAGE_ACCOUNT_NAME,
            account_key=account_key,
            container_name=container_name,
            blob_name=translated_blob_name,
            permission=BlobSasPermissions(read=True),
            expiry=datetime.utcnow() + timedelta(hours=1)
        )

        sas_url = f"https://{STORAGE_ACCOUNT_NAME}.blob.core.windows.net/{container_name}/{translated_blob_name}?{sas_token}"
        sas_urls.append({"file_name": translated_blob_name, "sas_url": sas_url})

        # get the original file name
        # original_file_name = re.sub(r"\(\d{5}\)$", "", translated_blob_name)

        sas_data = []
        sas_data.append({
            "file_name": translated_blob_name,
            "sas_url": sas_url,
        })        

        # 6. Return the SAS URL for the uploaded translated document
        return jsonify({"sas_data": sas_data,"Status":"Succeded"})

    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True)
