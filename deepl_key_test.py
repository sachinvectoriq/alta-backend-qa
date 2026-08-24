# deepl_key_test.py

import deepl
from flask import jsonify, request

def test_api_key(auth_key):
    # Hardcoded values inside the function
    text = "Hello, how are you?"  # Text to be translated
    target_language = "French"    # Target language for translation
    source_language = "English"   # Source language for translation
    formality = 'default'         # Optional formality parameter
    preserve_formatting = True    # Optional formatting preservation
    
    # Language mapping
    language_mapping = {
        "English": "EN",
        "French": "FR"
    }

    # Validate the provided API key
    if not auth_key:
        raise ValueError("Missing required parameter: 'auth_key'.")

    # Initialize the DeepL translator with the provided API key
    translator = deepl.Translator(auth_key)

    # Get language codes from hardcoded names
    source_lang = language_mapping.get(source_language)
    target_lang = language_mapping.get(target_language)

    try:
        # Perform translation using DeepL API
        result = translator.translate_text(
            text,
            source_lang=source_lang,
            target_lang=target_lang,
            formality=formality if formality != 'default' else None,
            preserve_formatting=preserve_formatting
        )
        return result.text
    except deepl.DeepLException as e:
        raise RuntimeError(f"Translation failed: {str(e)}")

def check_api_key():
    if request.content_type != 'application/json':
        return jsonify({'error': 'Content-Type must be application/json'}), 400

    # Get JSON data from the request
    data = request.get_json()

    if not data:
        return jsonify({'error': 'Request body must be in JSON format'}), 400

    # Extract the DeepL API key from the request
    auth_key = data.get('auth_key')
    if not auth_key:
        return jsonify({'error': 'Please provide the "auth_key".'}), 400

    try:
        # Test the API key by performing a translation
        translated_text = test_api_key(auth_key)
        return jsonify({'success': True, 'translated_text': translated_text}), 200
    except ValueError as ve:
        return jsonify({'error': str(ve)}), 400
    except RuntimeError as re:
        return jsonify({'error': str(re)}), 500
    except Exception as e:
        return jsonify({'error': 'An unexpected error occurred: ' + str(e)}), 500
