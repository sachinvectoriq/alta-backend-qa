'''
import os
import requests
import psycopg2
# Import extensions module to correctly reference the cursor type for type hinting
from psycopg2.extensions import cursor as CursorType
from typing import List, Dict, Any


# --- Database Utility ---

# CORRECTED: Changed psycopg2.cursor to CursorType (or psycopg2.extensions.cursor)
def get_deepl_api_key(cursor: CursorType) -> str:
    """
    Fetches the DeepL API key from the 'settings' table.
    """
    query = "SELECT api_key FROM deepl_settings WHERE admin_id = '1';"
    cursor.execute(query)

    result = cursor.fetchone()
    if result:
        return result[0]
    else:
        raise ValueError("DeepL API Key not found in the 'settings' table under key 'DEEPL_AUTH_KEY'.")


# --- DeepL API Utilities (Source and Target Endpoints) ---

def get_deepl_target_languages(auth_key: str) -> List[Dict[str, Any]]:
    """Fetches DeepL Target languages."""
    url = "https://api.deepl.com/v2/languages"
    headers = {
        "Authorization": f"DeepL-Auth-Key {auth_key}"
    }
    params = {
        "type": "target"
    }
    response = requests.get(url, headers=headers, params=params)

    if response.status_code == 200:
        return response.json()
    else:
        error_message = f"Failed to fetch target languages: {response.status_code} - {response.text}"
        raise requests.exceptions.HTTPError(error_message)


def get_deepl_source_languages(auth_key: str) -> List[Dict[str, Any]]:
    """Fetches DeepL Source languages."""
    url = "https://api.deepl.com/v2/languages"
    headers = {
        "Authorization": f"DeepL-Auth-Key {auth_key}"
    }
    params = {
        "type": "source"
    }
    response = requests.get(url, headers=headers, params=params)

    if response.status_code == 200:
        return response.json()
    else:
        error_message = f"Failed to fetch source languages: {response.status_code} - {response.text}"
        raise requests.exceptions.HTTPError(error_message)


# --- Main Execution ---

if __name__ == "__main__":

    connection = None
    cursor = None
    try:
        # 1. Establish database connection using environment variablesDB_HOST=c-settings-details.4frco7jk32qfsk.postgres.cosmos.azure.com
        # DB_NAME=settings_db
        # DB_PASSWORD=password@123
        # DB_PORT=5432
        # DB_USER=citus

        connection = psycopg2.connect(
            database='settings_db',
            user= 'citus',
            password='password@123',
            host='c-settings-details.4frco7jk32qfsk.postgres.cosmos.azure.com',
            port=os.getenv('DB_PORT')
        )
        # 2. IMPORTANT: The cursor object is created from the connection instance
        cursor = connection.cursor()

        # 3. Retrieve DeepL API Key
        API_KEY = get_deepl_api_key(cursor)

        # Fetch Target Languages
        print("\n--- Fetching Target Languages ---")
        target_languages = get_deepl_target_languages(API_KEY)
        print(f"Fetched {len(target_languages)} target languages.",target_languages)

        # Fetch Source Languages
        print("\n--- Fetching Source Languages ---")
        source_languages = get_deepl_source_languages(API_KEY)
        print(f"Fetched {len(source_languages)} source languages.",source_languages)

    except psycopg2.Error as e:
        print(f"Database connection or query error: {e}")
    except requests.exceptions.RequestException as e:
        print(f"DeepL API request error: {e}")
    except ValueError as e:
        print(f"Configuration error: {e}")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
    finally:
        # 5. Cleanup connection
        if cursor:
            cursor.close()
        if connection:
            connection.close()
            print("\nDatabase connection closed.")
            '''

import os
import requests
import psycopg2
from psycopg2.extensions import cursor as CursorType
from typing import List, Dict, Any, Optional


# --- Configuration & Helper Utilities ---

def fetch_deepl_api_key() -> str:
    """
    Establishes and closes the database connection, then retrieves the DeepL API key.

    Returns:
        The DeepL authentication key as a string.

    Raises:
        psycopg2.Error: If the database connection or query fails.
        ValueError: If the API key is not found in the settings table.
    """
    connection = None
    try:
        # 1. Establish database connection using environment variables
        connection = psycopg2.connect(
            database='settings_db',
            user= 'citus',
            password='password@123',
            host='c-settings-details.4frco7jk32qfsk.postgres.cosmos.azure.com',
            port=os.getenv('DB_PORT')
        )
        cursor = connection.cursor()

        # 2. Retrieve DeepL API Key from the 'settings' table
        query = "SELECT api_key FROM deepl_settings WHERE admin_id = '1';"
        cursor.execute(query)

        result = cursor.fetchone()
        cursor.close()

        if result:
            return result[0]
        else:
            raise ValueError("DeepL API Key not found in 'deeplsettings' table.")

    finally:
        # 3. Ensure the database connection is closed
        if connection:
            connection.close()


def get_deepl_endpoint(auth_key: str, lang_type: str) -> List[Dict[str, Any]]:
    """
    Fetches languages (source or target) from the DeepL API for a single endpoint call.
    """
    url = "https://api.deepl.com/v2/languages"
    headers = {
        "Authorization": f"DeepL-Auth-Key {auth_key}"
    }
    params = {
        "type": lang_type
    }
    response = requests.get(url, headers=headers, params=params)

    if response.status_code == 200:
        return response.json()
    else:
        error_message = f"Failed to fetch {lang_type} languages: {response.status_code} - {response.text}"
        # Raising requests.exceptions.HTTPError is more robust for API errors
        raise requests.exceptions.HTTPError(error_message)


# --- Public API Function ---

def get_all_deepl_languages() -> Dict[str, Dict[str, List[Dict[str, Any]]]]:
    """
    Fetches both source and target languages from the DeepL API.

    This function handles the entire process: fetching the key, calling both endpoints,
    and closing the database connection.

    Returns:
        A dictionary in the required format:
        {'deepllanguages': {'source': [list of source languages], 'target': [list of target languages]}}

    Raises:
        Exception: Captures and raises errors from DB connection, key retrieval, or API calls.
    """
    try:
        # 1. Fetch API Key (DB connection/closure happens inside this function)
        API_KEY = fetch_deepl_api_key()

        # 2. Fetch Source and Target Languages concurrently
        source_languages = get_deepl_endpoint(API_KEY, "source")
        target_languages = get_deepl_endpoint(API_KEY, "target")

        # 3. Format and return the final dictionary structure
        return {
            "deepllanguages": {
                "source": source_languages,
                "target": target_languages
            }
        }

    except Exception as e:
        # Re-raise the exception after logging (if necessary)
        # This centralizes error handling for the calling application
        print(f"An error occurred during language fetching: {e}")
        raise


# --- Main Execution ---

if __name__ == "__main__":

    languages_data = get_all_deepl_languages()
