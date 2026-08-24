# from flask import Flask, request, jsonify
# import requests
# import csv
# import io
# from io import BytesIO
# import os


# app = Flask(__name__)

# # Language mapping as provided
# language_mapping = {
#     "Arabic": "AR",
#     "Bulgarian": "BG",
#     "Czech": "CS",
#     "Danish": "DA",
#     "German": "DE",
#     "Greek": "EL",
#     "English": "EN",
#     "English (British)": "EN-GB",
#     "English (American)": "EN-US",
#     "Spanish": "ES",
#     "Estonian": "ET",
#     "Finnish": "FI",
#     "French": "FR",
#     "Hungarian": "HU",
#     "Indonesian": "ID",
#     "Italian": "IT",
#     "Japanese": "JA",
#     "Korean": "KO",
#     "Lithuanian": "LT",
#     "Latvian": "LV",
#     "Norwegian Bokmål": "NB",
#     "Dutch": "NL",
#     "Polish": "PL",
#     "Portuguese": "PT",
#     "Portuguese (Brazilian)": "PT-BR",
#     "Portuguese (European)": "PT-PT",
#     "Romanian": "RO",
#     "Russian": "RU",
#     "Slovak": "SK",
#     "Slovenian": "SL",
#     "Swedish": "SV",
#     "Turkish": "TR",
#     "Ukrainian": "UK",
#     "Chinese": "ZH",
#     "Chinese (Simplified)": "ZH-HANS",
#     "Chinese (Traditional)": "ZH-HANT"
# }


# def create_glossary(source_lang, target_lang, file):
#     # Hardcoded DeepL auth key and glossary name
#     auth_key = os.getenv('DEEPL_API_KEY')
#     glossary_name = "glossary"
    
#     # Set the URL for DeepL API glossary creation
#     url = os.getenv('DEEPL_API_GLOSSARY_URL')

#     # Set up headers
#     headers = {
#         "Authorization": f"DeepL-Auth-Key {auth_key}",
#         "Content-Type": "application/json",
#         "User-Agent": "YourApp/1.2.3"
#     }

#     # Read and format entries from the uploaded file
#     entries = ""
#     file_extension = file.filename.split('.')[-1]
    
#     file_contents = file.read()  # Read as bytes
#     file_io = BytesIO(file_contents)
    
#     # Read the file based on its extension
#     if file_extension == "csv":
#         reader = csv.reader(io.TextIOWrapper(file_io, encoding="utf-8"))
#     elif file_extension == "tsv":
#         reader = csv.reader(io.TextIOWrapper(file_io, encoding="utf-8"), delimiter='\t')
#     else:
#         return {"error": "Unsupported file format. Use CSV or TSV files."}

#     # Process each row and create the TSV formatted string for DeepL
#     for row in reader:
#         if len(row) >= 2:
#             # Ensure each entry is formatted correctly with a tab separator
#             entries += f"{row[0]}\t{row[1]}\n"

#     entries = entries.strip()  # Trim the last newline

#     # Debugging: Inspect the entries
#     print(f"Formatted entries (TSV): {entries}")

#     # Define the glossary payload
#     payload = {
#         "name": glossary_name,
#         "source_lang": source_lang,
#         "target_lang": target_lang,
#         "entries": entries,
#         "entries_format": "tsv"  # Make sure the format is set as "tsv"
#     }

#     # Make the POST request to DeepL API
#     response = requests.post(url, headers=headers, json=payload)

#     # Return success or error based on the response
#     if response.status_code == 201:
#         return response.json()  # return the JSON data directly
#     else:
#         # Log the full response for debugging purposes
#         response_data = response.json()
#         print(f"Error response: {response_data}")
#         return {"error": response_data, "status_code": response.status_code}



# # @app.route('/upload_glossary', methods=['POST'])
# def upload_glossary(source_lang,target_lang,file):

#     source_lang_code = language_mapping.get(source_lang, 'auto')
#     target_lang_code = language_mapping.get(target_lang)

#     # Validate form data
#     if not all([source_lang_code, target_lang_code, file]):
#         return jsonify({"error": "Missing required parameters"}), 400

#     # Call the create_glossary function
#     result = create_glossary(source_lang_code, target_lang_code, file)
#     return result

# if __name__ == '__main__':
#     app.run(debug=True)





















from flask import Flask, request, jsonify
import requests
import csv
import io
from io import BytesIO
import os
import logging
import psycopg2


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





global DEEPL_API_KEY, storage_connection_string2

DEEPL_API_KEY=None
storage_connection_string2=None


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
















def create_glossary(source_lang, target_lang, file):




    DEEPL_API_KEY, storage_connection_string2 = retrieve_settings()
    if not DEEPL_API_KEY or not storage_connection_string2:
        return jsonify({"error": "Failed to retrieve DEEPL_API_KEY"}), 500



    # Hardcoded DeepL auth key and glossary name
    auth_key = DEEPL_API_KEY
    glossary_name = "glossary"
    
    # Set the URL for DeepL API glossary creation
    url = os.getenv('DEEPL_API_GLOSSARY_URL')

    # Set up headers
    headers = {
        "Authorization": f"DeepL-Auth-Key {auth_key}",
        "Content-Type": "application/json",
        "User-Agent": "YourApp/1.2.3"
    }

    # Read and format entries from the uploaded file
    entries = ""
    file_extension = file.filename.split('.')[-1]
    
    file_contents = file.read()  # Read as bytes
    file_io = BytesIO(file_contents)
    
    # Read the file based on its extension
    if file_extension == "csv":
        reader = csv.reader(io.TextIOWrapper(file_io, encoding="utf-8"))
    elif file_extension == "tsv":
        reader = csv.reader(io.TextIOWrapper(file_io, encoding="utf-8"), delimiter='\t')
    else:
        return {"error": "Unsupported file format. Use CSV or TSV files."}

    # Process each row and create the TSV formatted string for DeepL
    for row in reader:
        if len(row) >= 2:
            # Ensure each entry is formatted correctly with a tab separator
            entries += f"{row[0]}\t{row[1]}\n"

    entries = entries.strip()  # Trim the last newline

    # Debugging: Inspect the entries
    print(f"Formatted entries (TSV): {entries}")

    # Define the glossary payload
    payload = {
        "name": glossary_name,
        "source_lang": source_lang,
        "target_lang": target_lang,
        "entries": entries,
        "entries_format": "tsv"  # Make sure the format is set as "tsv"
    }

    # Make the POST request to DeepL API
    response = requests.post(url, headers=headers, json=payload)

    # Return success or error based on the response
    if response.status_code == 201:
        return response.json()  # return the JSON data directly
    else:
        # Log the full response for debugging purposes
        response_data = response.json()
        print(f"Error response: {response_data}")
        return {"error": response_data, "status_code": response.status_code}



# @app.route('/upload_glossary', methods=['POST'])
def upload_glossary(source_lang,target_lang,file):

    source_lang_code = language_mapping.get(source_lang, 'auto')
    target_lang_code = language_mapping.get(target_lang)

    # Validate form data
    if not all([source_lang_code, target_lang_code, file]):
        return jsonify({"error": "Missing required parameters"}), 400

    # Call the create_glossary function
    result = create_glossary(source_lang_code, target_lang_code, file)
    return result

if __name__ == '__main__':
    app.run(debug=True)

