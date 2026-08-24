# import deepl
# import os
# from flask import jsonify

# # DeepL API key
# DEEPL_API_KEY = os.getenv('DEEPL_API_KEY')
# translator = deepl.Translator(DEEPL_API_KEY)

# # Language mapping
# language_mapping = {
#     "Arabic": "AR",
#     "Bulgarian": "BG",
#     "Czech": "CS",
#     "Danish": "DA",
#     "German": "DE",
#     "Greek": "EL",
#     "English": "EN",  # General English
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
#     "Portuguese": "PT",  # General Portuguese
#     "Portuguese (Brazilian)": "PT-BR",
#     "Portuguese (European)": "PT-PT",
#     "Romanian": "RO",
#     "Russian": "RU",
#     "Slovak": "SK",
#     "Slovenian": "SL",
#     "Swedish": "SV",
#     "Turkish": "TR",
#     "Ukrainian": "UK",
#     "Chinese": "ZH",  # General Chinese
#     "Chinese (Simplified)": "ZH-HANS",
#     "Chinese (Traditional)": "ZH-HANT"
# }

# # Supported languages for formality
# formality_supported_languages = {"DE", "FR", "IT", "ES", "NL", "PL", "PT-BR", "PT-PT", "JA", "RU"}

# def translate_text(text, target_lang_name, source_lang_name=None, formality='default', preserve_formatting=True):
#     """Performs the translation using DeepL API."""
#     if not text or not target_lang_name:
#         raise ValueError("Missing required parameters: 'text' and 'target_lang'.")

#     # Convert language names to codes
#     source_lang = language_mapping.get(source_lang_name) if source_lang_name else None
#     target_lang = language_mapping.get(target_lang_name)

#     if target_lang is None:
#         raise ValueError(f"Invalid target language: '{target_lang_name}'. Please provide a valid language name.")

#     try:
#         # Perform the translation
#         result = translator.translate_text(
#             text,
#             source_lang=source_lang,
#             target_lang=target_lang,
#             formality=formality,
#             preserve_formatting=True  # Always true
#         )
#         return result.text
#     except Exception as e:
#         raise RuntimeError(f"Translation failed: {str(e)}")

# def handle_translation_request(data):
#     """Handles the translation request and returns the appropriate response."""
#     text = data.get('text')
#     target_language = data.get('target_language')
#     source_language = data.get('source_language', None)

#     if not text or not target_language:
#         return jsonify({'error': 'Please provide text and target_language'}), 400

#     formality = data.get('formality', 'default')

#     try:
#         # Perform translation
#         translated_text = translate_text(text, target_language, source_language, formality)
#         return jsonify({'translated_text': translated_text})
#     except Exception as e:
#         return jsonify({'error': str(e)}), 500




import deepl
import os
from flask import jsonify, request
import logging
import psycopg2

# DeepL API key
# DEEPL_API_KEY = os.getenv('DEEPL_API_KEY')
# translator = deepl.Translator(DEEPL_API_KEY)

# Language mapping
language_mapping = {
    "Arabic": "AR",
    "Bulgarian": "BG",
    "Czech": "CS",
    "Danish": "DA",
    "German": "DE",
    "Greek": "EL",
    "English": "EN",  # General English
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
    "Portuguese": "PT",  # General Portuguese
    "Portuguese (Brazilian)": "PT-BR",
    "Portuguese (European)": "PT-PT",
    "Romanian": "RO",
    "Russian": "RU",
    "Slovak": "SK",
    "Slovenian": "SL",
    "Swedish": "SV",
    "Turkish": "TR",
    "Ukrainian": "UK",
    "Chinese": "ZH",  # General Chinese
    "Chinese (Simplified)": "ZH-HANS",
    "Chinese (Traditional)": "ZH-HANT"
}

# Supported languages for formality
formality_supported_languages = {"DE", "FR", "IT", "ES", "NL", "PL", "PT-BR", "PT-PT", "JA", "RU"}


global DEEPL_API_KEY, storage_connection_string2
DEEPL_API_KEY= None
storage_connection_string2 = None

def retrieve_settings():
    global storage_connection_string2 , DEEPL_API_KEY

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

        DEEPL_API_KEY= result_deepl_settings[0]

        logging.info("Settings retrieved successfully.")
        
        cursor.close()
        connection.close()

        return DEEPL_API_KEY, storage_connection_string2

    except Exception as e:
        logging.error(f"Error retrieving settings: {e}")
        return None, None


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



def translate_text(text, target_lang_name, source_lang_name=None, formality='default', preserve_formatting=True):
    """Performs the translation using DeepL API."""
    if not text or not target_lang_name:
        raise ValueError("Missing required parameters: 'text' and 'target_lang'.")


    DEEPL_API_KEY, storage_connection_string2 = retrieve_settings()
    if not DEEPL_API_KEY or not storage_connection_string2:
        return jsonify({"error": "Failed to retrieve required settings"}), 500
    translator = deepl.Translator(DEEPL_API_KEY)


    # Convert language names to codes
    source_lang = language_mapping.get(source_lang_name) if source_lang_name else None
    target_lang = language_mapping.get(target_lang_name)

    if target_lang is None:
        raise ValueError(f"Invalid target language: '{target_lang_name}'. Please provide a valid language name.")
    try:
        # Perform the translation
        result = translator.translate_text(
            text,
            source_lang=source_lang,
            target_lang=target_lang,
            formality=formality,
            preserve_formatting=True  # Always true
        )
        # Return a dict instead of just result.text
        return {
            "translated_text": result.text,
            "detected_source_lang": result.detected_source_lang,
            "billed_characters": result.billed_characters,
        }
    except Exception as e:
        raise RuntimeError(f"Translation failed: {str(e)}")

def handle_translation_request(data):

    # auth_error = validate_bearer_token(request, 'A7x!G2p@Q9#L')  # Replace 'pass123' with your actual token
    # if auth_error:
    #     return auth_error



  
    """Handles the translation request and returns the appropriate response."""
    text = data.get('text')
    target_language = data.get('target_language')
    source_language = data.get('source_language', None)

    if not text or not target_language:
        return jsonify({'error': 'Please provide text and target_language'}), 400

    formality = data.get('formality', 'default')

    try:
        # Perform translation
        translation_result = translate_text(text, target_language, source_language, formality)
        return jsonify({
            'translated_text': translation_result['translated_text'],
            'detected_source_lang': translation_result['detected_source_lang'],
            'billed_characters': translation_result['billed_characters'],
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

