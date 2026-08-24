import datetime
# import logging # Removed existing logging import
from azure.storage.blob import BlobServiceClient
from flask import jsonify
import os
from logging_config import log, flush  # Import log and flush functions

# Retrieve the connection string (replace with your actual environment variable if necessary)
connection_string = os.getenv('STORAGE_CONNECTION_STRING')
# Configure logging - No longer needed as we're using logging_config
# logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Check if the connection string is set
if not connection_string:
    log("CRITICAL", "STORAGE_CONNECTION_STRING environment variable is not set.")
    flush()  # Flush immediately for critical configuration error
    raise ValueError("Please set the STORAGE_CONNECTION_STRING environment variable.")


def get_container_timestamp(container_name: str, user_name: str = None):
    # Extract timestamp from container name, assuming format 'source-YYYYMMDDHHMMSS'
    try:
        timestamp_str = container_name.split('-')[-1]
        timestamp = datetime.datetime.strptime(timestamp_str, '%Y%m%d%H%M%S')
        log("INFO", f"Successfully extracted timestamp from container name: {container_name}",
            data={"timestamp": timestamp.isoformat()}, user_name=user_name)
        return timestamp
    except ValueError as e:
        log("WARNING",
            f"Container {container_name} does not match the expected naming pattern (YYYYMMDDHHMMSS suffix). Error: {e}",
            user_name=user_name)
        return None


def delete_old_containers(user_name: str = None):
    log("INFO", "Initiating deletion process for old Azure Blob Storage containers.", user_name=user_name)

    # Create BlobServiceClient using the connection string
    try:
        blob_service_client = BlobServiceClient.from_connection_string(connection_string)
        log("INFO", "BlobServiceClient created successfully.", user_name=user_name)
    except Exception as e:
        log("CRITICAL", f"Failed to create BlobServiceClient. Check STORAGE_CONNECTION_STRING. Error: {e}",
            user_name=user_name)
        flush()  # Flush immediately on critical client creation failure
        return jsonify({"error": f"Failed to connect to Azure Storage: {e}"}), 500

    # Get current time
    current_time = datetime.datetime.utcnow()
    log("INFO", f"Current UTC Time: {current_time.isoformat()}", user_name=user_name)

    # List all containers in the storage account
    deleted_containers = []
    try:
        containers = blob_service_client.list_containers()
        log("INFO", "Successfully listed containers from Azure Storage.", user_name=user_name)
    except Exception as e:
        log("ERROR", f"Failed to list containers in storage account: {e}", user_name=user_name)
        flush()  # Flush immediately on container listing failure
        return jsonify({"error": f"Failed to list containers: {e}"}), 500

    for container in containers:
        container_name = container['name']
        log("INFO", f"Processing container: {container_name}", user_name=user_name)

        # Get the timestamp from the container name
        container_timestamp = get_container_timestamp(container_name, user_name)

        if container_timestamp:
            # Check if the container is older than fifteen minutes (900 seconds)
            time_difference = current_time - container_timestamp
            if time_difference.total_seconds() > 900:  # Older than 15 minutes
                try:
                    # Delete the container
                    blob_service_client.delete_container(container_name)
                    deleted_containers.append(container_name)
                    log("INFO", f"Successfully deleted container: {container_name}", user_name=user_name)
                except Exception as e:
                    log("ERROR", f"Failed to delete container {container_name}: {e}", user_name=user_name)
                    flush()  # Flush immediately on individual container deletion failure
            else:
                log("INFO", f"Container {container_name} is less than 15 minutes old, skipping deletion.",
                    user_name=user_name)
        else:
            log("INFO",
                f"Container {container_name} does not match the expected naming pattern, skipping timestamp check.",
                user_name=user_name)

    log("INFO", f"Container deletion process completed. Deleted {len(deleted_containers)} containers.",
        data={"deleted_containers_count": len(deleted_containers)}, user_name=user_name)
    return jsonify({"deleted_containers": deleted_containers}), 200
