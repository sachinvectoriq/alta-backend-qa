import datetime
import logging
from azure.storage.blob import BlobServiceClient
from flask import Flask, jsonify
import os

app = Flask(__name__)

# Retrieve the connection string (replace with your actual environment variable if necessary)
connection_string = os.getenv('STORAGE_CONNECTION_STRING')

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Check if the connection string is set
if not connection_string:
    logging.error("STORAGE_CONNECTION_STRING environment variable is not set.")
    raise ValueError("Please set the STORAGE_CONNECTION_STRING environment variable.")

# Define the container name
CONTAINER_NAME = "deepl-container"

@app.route('/delete_old_files', methods=['DELETE'])
def delete_old_files_in_container():
    logging.info("Deleting files in 'deepl-container' older than 15 minutes")

    # Create BlobServiceClient using the connection string
    blob_service_client = BlobServiceClient.from_connection_string(connection_string)

    # Get the container client
    container_client = blob_service_client.get_container_client(CONTAINER_NAME)

    # Get current time
    current_time = datetime.datetime.utcnow()
    logging.info(f"Current UTC Time: {current_time}")

    deleted_files = []

    try:
        # List all blobs (files) in the container
        blobs = container_client.list_blobs()

        for blob in blobs:
            # Get the last modified time of the blob
            last_modified = blob['last_modified']

            # Calculate the time difference
            time_difference = current_time - last_modified.replace(tzinfo=None)

            # Delete the blob if it is older than 15 minutes (900 seconds)
            if time_difference.total_seconds() > 900:
                try:
                    # Delete the blob (file)
                    container_client.delete_blob(blob['name'])
                    deleted_files.append(blob['name'])
                    logging.info(f"Deleted file: {blob['name']}")
                except Exception as e:
                    logging.error(f"Failed to delete file {blob['name']}: {e}")
            else:
                logging.info(f"File {blob['name']} is less than 15 minutes old, skipping...")

    except Exception as e:
        logging.error(f"Failed to list or delete blobs in the container: {e}")
        return jsonify({"error": str(e)}), 500

    return jsonify({"deleted_files": deleted_files}), 200

if __name__ == '__main__':
    # Run the Flask app on localhost at port 5000
    app.run(host='0.0.0.0', port=5000, debug=True)
