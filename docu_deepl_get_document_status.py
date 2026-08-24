from flask import Flask, request, jsonify
import requests
import os

app = Flask(__name__)

DEEPL_API_KEY = os.getenv('DEEPL_API_KEY')
DEEPL_BASE_URL = os.getenv('DEEPL_DOCUMENT_TRANSLATION_URL')



@app.route('/check_status', methods=['POST'])
def check_status():
    try:
        # Parse the JSON input
        input_data = request.json

        # Validate input data
        if not isinstance(input_data, list) or len(input_data) == 0:
            return jsonify({'error': 'Input should be a list of dictionaries with file_name, document_id, and document_key'}), 400

        # Initialize an empty list for results
        results = []

        # Iterate over each input group
        for group in input_data:
            file_name = group.get('file_name')
            document_id = group.get('document_id')
            document_key = group.get('document_key')

            # Check for missing fields
            if not file_name or not document_id or not document_key:
                results.append({
                    'file_name': file_name or 'Unknown',
                    'error': 'Missing document_id or document_key'
                })
                continue

            # Prepare the request URL and parameters
            url = f"{DEEPL_BASE_URL}/{document_id}"
            headers = {'Authorization': f"DeepL-Auth-Key {DEEPL_API_KEY}"}
            params = {'document_key': document_key}

            # Send the request to DeepL API
            response = requests.get(url, headers=headers, params=params)
            response_data = response.json()

            # Process the response
            if response.status_code == 200:
                results.append({
                    'file_name': file_name,
                    'document_id':document_id,
                    'document_key':document_key,
                    'status': response_data.get('status'),
                    'seconds_remaining': response_data.get('seconds_remaining'),
                    'billed_characters': response_data.get('billed_characters')
                })
            else:
                results.append({
                    'file_name': file_name,
                    'error': response_data.get('message', 'Unknown error')
                })

        # Return the aggregated results
        return jsonify(results), 200

    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True)
