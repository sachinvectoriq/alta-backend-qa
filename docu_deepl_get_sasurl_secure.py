# from datetime import datetime, timedelta
# from azure.storage.blob import BlobServiceClient, generate_blob_sas, BlobSasPermissions
# import requests
# from flask import Flask, request, jsonify
# import os
# import re
# import random

# app = Flask(__name__)

# # Constants
# DEEPL_API_URL = os.getenv('DEEPL_DOCUMENT_TRANSLATION_URL')
# DEEPL_API_KEY=os.getenv('DEEPL_API_KEY')
# STORAGE_ACCOUNT_NAME = os.getenv('STORAGE_SERVICE_ACCOUNT_NAME')
# sas_urls = []

# # Replace with your Azure Storage connection string and account key
# connection_string = os.getenv('STORAGE_CONNECTION_STRING')
# account_key = os.getenv('STORAGE_SERVICE_KEY')



# def validate_bearer_token(request, expected_token):
#     """
#     Validates the Bearer token from the Authorization header in the request.
#     Returns an error response if invalid; otherwise, returns None.
#     """
#     auth_header = request.headers.get('Authorization', '')
#     if not auth_header.startswith('Bearer '):
#         return jsonify({"error": "Invalid or missing Authorization header."}), 401
#     token = auth_header.split(' ')[1]
#     if token != expected_token:
#         return jsonify({"error": "Unauthorized. Invalid Bearer token."}), 403
#     return None  # No error


# @app.route('/download_translate_upload', methods=['POST'])
# def download_translate_upload_secure():
#     auth_error = validate_bearer_token(request, 'A7x!G2p@Q9#L')  # Replace 'A7x!G2p@Q9#L' with your actual token
#     if auth_error:
#         return auth_error

#     try:
#         # Get document_id and document_key from form data
#         document_id = request.form.get("document_id")
#         document_key = request.form.get("document_key")
#         translated_blob_name =request.form.get("file_name")

#         if not document_id or not document_key:
#             return jsonify({"error": "Both document_id and document_key are required."}), 400

#         # 1. Download the translated document
#         headers = {'Authorization': f'DeepL-Auth-Key {DEEPL_API_KEY}'}
#         download_response = requests.post(
#             f"{DEEPL_API_URL}/{document_id}/result",
#             json={"document_key": document_key},
#             headers=headers
#         )

#         if download_response.status_code != 200:
#             return jsonify({"error": f"Failed to download translated file: {download_response.text}"}), download_response.status_code


#         # Initialize BlobServiceClient
#         blob_service_client = BlobServiceClient.from_connection_string(connection_string)

#         # 3. Create a new container with a unique name
#         container_name = os.getenv('DEEPL_CONTAINER')

#         # 4. Upload the translated document to Azure Blob Storage
#         blob_client = blob_service_client.get_blob_client(container=container_name, blob=translated_blob_name)

#         # Check if the blob with the same name already exists
#         if blob_client.exists():
#             # Generate a random 3-digit number
#             random_number = random.randint(100, 999)
            
#             # Generate a new name for the blob
#             translated_blob_name = f"{translated_blob_name.rsplit('.', 1)[0]}-{random_number}.{translated_blob_name.rsplit('.', 1)[-1]}"
            
#             # Create a new BlobClient with the updated name
#             blob_client = blob_service_client.get_blob_client(container=container_name, blob=translated_blob_name)
        
#         # Upload the file to the container
#         blob_client.upload_blob(download_response.content, overwrite=True)


#         # 5. Generate a SAS URL for the uploaded blob
#         sas_token = generate_blob_sas(
#             account_name=STORAGE_ACCOUNT_NAME,
#             account_key=account_key,
#             container_name=container_name,
#             blob_name=translated_blob_name,
#             permission=BlobSasPermissions(read=True),
#             expiry=datetime.utcnow() + timedelta(hours=1)
#         )

#         sas_url = f"https://{STORAGE_ACCOUNT_NAME}.blob.core.windows.net/{container_name}/{translated_blob_name}?{sas_token}"
#         sas_urls.append({"file_name": translated_blob_name, "sas_url": sas_url})

#         # get the original file name
#         # original_file_name = re.sub(r"\(\d{5}\)$", "", translated_blob_name)

#         sas_data = []
#         sas_data.append({
#             "file_name": translated_blob_name,
#             "sas_url": sas_url,
#         })        

#         # 6. Return the SAS URL for the uploaded translated document
#         return jsonify({"sas_data": sas_data,"Status":"Succeded"})

#     except Exception as e:
#         return jsonify({"error": str(e)}), 500

# if __name__ == '__main__':
#     app.run(debug=True)










from datetime import datetime, timedelta
from azure.storage.blob import BlobServiceClient, generate_blob_sas, BlobSasPermissions
import requests
from flask import Flask, request, jsonify
import os
import re
import random
import logging
import psycopg2

app = Flask(__name__)

# Constants


global DEEPL_API_KEY, account_key, STORAGE_ACCOUNT_NAME, connection_string, admin_id, storage_connnection_string2

storage_connection_string2 = None

# DEEPL_API_KEY=os.getenv('DEEPL_API_KEY')
DEEPL_API_KEY=None


account_key = None
STORAGE_ACCOUNT_NAME = None
sas_urls = []

# Replace with your Azure Storage connection string and account key
# connection_string = os.getenv('STORAGE_CONNECTION_STRING')
connection_string = None





DEEPL_API_URL = os.getenv('DEEPL_DOCUMENT_TRANSLATION_URL')

admin_id=1










def retrieve_settings():
    global storage_connection_string2, DEEPL_API_KEY

    try:
        # Database connection
        connection = psycopg2.connect(
            database= os.getenv('DB_NAME'),  # 'settings_db' is the default if env variable is not set
            user=os.getenv('DB_USER'),
            password= os.getenv('DB_PASSWORD'),
            host= os.getenv('DB_HOST'),
            port= os.getenv('DB_PORT')
        )
        cursor = connection.cursor()

        logging.info("Connected to the database successfully.")

        # Query to fetch storage_connection_string from the settings table
        query_settings = """
        SELECT storage_connection_string
        FROM settings
        WHERE admin_id = %s;
        """
        cursor.execute(query_settings, ('1',))
        result_settings = cursor.fetchone()

        if not result_settings:
            logging.error("No settings found for Admin_id 1 in the 'settings' table.")
            return None, None

        storage_connection_string2 = result_settings[0]

        # Query to fetch api_key from the deepl_settings table
        query_deepl_settings = """
        SELECT api_key
        FROM deepl_settings
        WHERE admin_id = %s;
        """
        cursor.execute(query_deepl_settings, ('1',))
        result_deepl_settings = cursor.fetchone()

        if not result_deepl_settings:
            logging.error("No settings found for Admin_id 1 in the 'deepl_settings' table.")
            return None, None

        DEEPL_API_KEY = result_deepl_settings[0]

        logging.info("Settings retrieved successfully.")
        
        cursor.close()
        connection.close()

        return DEEPL_API_KEY, storage_connection_string2

    except Exception as e:
        logging.error(f"Error retrieving settings: {e}")
        return None, None


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
    global STORAGE_ACCOUNT_NAME, account_key, connection_string
    try:
        account_name_start = connection_string.find("AccountName=") + len("AccountName=")
        account_name_end = connection_string.find(";", account_name_start)
        account_key_start = connection_string.find("AccountKey=") + len("AccountKey=")
        account_key_end = connection_string.find(";", account_key_start)

        STORAGE_ACCOUNT_NAME = connection_string[account_name_start:account_name_end]
        account_key = connection_string[account_key_start:account_key_end]

        logging.info(f"Storage account name extracted: {STORAGE_ACCOUNT_NAME}")
        logging.info("Storage account key extracted.")
    except Exception as ex:
        logging.error(f"Failed to parse storage account details: {ex}")

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


@app.route('/download_translate_upload', methods=['POST'])
def download_translate_upload_secure():


    DEEPL_API_KEY, storage_connection_string2 = retrieve_settings()
    if not DEEPL_API_KEY or not storage_connection_string2:
        return jsonify({"error": "Failed to retrieve DEEPL_API_KEY"}), 500
    print(DEEPL_API_KEY)



    if not get_settings():
        return jsonify({"message": "Failed to retrieve settings."}), 500

    # Parse the storage account details
    parse_storage_account_details()





    auth_error = validate_bearer_token(request, 'A7x!G2p@Q9#L')  # Replace 'A7x!G2p@Q9#L' with your actual token
    if auth_error:
        return auth_error

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

