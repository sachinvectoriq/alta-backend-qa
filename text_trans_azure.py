from flask import Flask, request, jsonify
import logging
import requests
import uuid
import psycopg2
import os
import threading

from requests.adapters import HTTPAdapter
from psycopg2.pool import ThreadedConnectionPool


# ============================================================
# APP
# ============================================================

app = Flask(__name__)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s"
)


# ============================================================
# DATABASE CONFIGURATION
# ============================================================

host = os.getenv("DB_HOST")
database = os.getenv("DB_NAME")
user = os.getenv("DB_USER")
password = os.getenv("DB_PASSWORD")
port = os.getenv("DB_PORT")

ADMIN_ID = "1"

DB_POOL_MIN = int(
    os.getenv("DB_POOL_MIN", "2")
)

DB_POOL_MAX = int(
    os.getenv("DB_POOL_MAX", "20")
)


# ============================================================
# TRANSLATOR HTTP CONFIGURATION
# ============================================================

HTTP_POOL_SIZE = int(
    os.getenv("TRANSLATOR_HTTP_POOL_SIZE", "200")
)

HTTP_CONNECT_TIMEOUT = float(
    os.getenv("TRANSLATOR_CONNECT_TIMEOUT", "5")
)

HTTP_READ_TIMEOUT = float(
    os.getenv("TRANSLATOR_READ_TIMEOUT", "60")
)

HTTP_TIMEOUT = (
    HTTP_CONNECT_TIMEOUT,
    HTTP_READ_TIMEOUT
)


# ============================================================
# HTTP CONNECTION POOL
# ============================================================

http_session = requests.Session()

http_adapter = HTTPAdapter(
    pool_connections=HTTP_POOL_SIZE,
    pool_maxsize=HTTP_POOL_SIZE,
    max_retries=0,
    pool_block=False
)

http_session.mount(
    "https://",
    http_adapter
)

http_session.mount(
    "http://",
    http_adapter
)


# ============================================================
# DATABASE CONNECTION POOL
# ============================================================

db_pool = None
db_pool_lock = threading.Lock()


def initialize_db_pool():

    global db_pool

    if db_pool is not None:
        return

    with db_pool_lock:

        if db_pool is not None:
            return

        try:

            db_pool = ThreadedConnectionPool(
                DB_POOL_MIN,
                DB_POOL_MAX,
                host=host,
                database=database,
                user=user,
                password=password,
                port=port,
                sslmode="require"
            )

            logging.info(
                "PostgreSQL connection pool initialized. "
                "min=%s max=%s",
                DB_POOL_MIN,
                DB_POOL_MAX
            )

        except Exception:

            logging.exception(
                "Failed to initialize PostgreSQL connection pool."
            )

            raise


# ============================================================
# SETTINGS CACHE
# ============================================================

_settings_cache = None
_settings_lock = threading.Lock()


def fetch_settings(admin_id):

    global _settings_cache

    # --------------------------------------------------------
    # FIRST: use cached settings
    # --------------------------------------------------------

    with _settings_lock:

        if _settings_cache is not None:

            return _settings_cache

    # --------------------------------------------------------
    # CACHE EMPTY:
    # fall back to database
    # --------------------------------------------------------

    if db_pool is None:

        initialize_db_pool()

    conn = None
    cursor = None

    try:

        conn = db_pool.getconn()

        cursor = conn.cursor()

        query = """
        SELECT key, text_translation_endpoint, region
        FROM settings
        WHERE admin_id = %s;
        """

        cursor.execute(
            query,
            (admin_id,)
        )

        result = cursor.fetchone()

        if result is None:

            logging.error(
                "No settings found for admin_id=%s",
                admin_id
            )

            return None

        # ----------------------------------------------------
        # Cache settings for future requests
        # ----------------------------------------------------

        with _settings_lock:

            _settings_cache = result

        logging.info(
            "Settings loaded from database and cached."
        )

        return result

    except Exception as e:

        logging.error(
            "Database error occurred: %s",
            e,
            exc_info=True
        )

        return None

    finally:

        if cursor is not None:

            try:
                cursor.close()
            except Exception:
                pass

        if conn is not None:

            try:
                db_pool.putconn(conn)
            except Exception:
                pass


# ============================================================
# LANGUAGE CACHE
# ============================================================

_language_cache = {}

_language_cache_lock = threading.RLock()


def get_supported_languages(
    endpoint,
    api_key
):

    try:

        url = (
            f"{endpoint.rstrip('/')}"
            "/languages?api-version=3.0"
        )

        headers = {
            "Ocp-Apim-Subscription-Key": api_key,
            "Content-Type": "application/json"
        }

        response = http_session.get(
            url,
            headers=headers,
            timeout=HTTP_TIMEOUT
        )

        response.raise_for_status()

        return response.json()

    except requests.exceptions.RequestException as e:

        logging.error(
            "Failed to retrieve supported languages: %s",
            e,
            exc_info=True
        )

        raise


def build_language_cache(
    supported_languages
):

    translation_languages = (
        supported_languages.get("translation")
        or {}
    )

    new_cache = {}

    for code, language_info in (
        translation_languages.items()
    ):

        name = language_info.get(
            "name"
        )

        native_name = language_info.get(
            "nativeName"
        )

        if name:

            new_cache[
                name.strip().lower()
            ] = code

        if native_name:

            new_cache[
                native_name.strip().lower()
            ] = code

    with _language_cache_lock:

        _language_cache.clear()

        _language_cache.update(
            new_cache
        )

    logging.info(
        "Loaded %s supported language mappings.",
        len(new_cache)
    )


def get_language_code(
    language_name,
    endpoint=None,
    api_key=None
):

    """
    Resolve language name to Azure language code.

    Normal path:
        memory cache -> immediate lookup

    Fallback path:
        if cache is empty/missing the language,
        call /languages once, rebuild cache, and retry.

    This prevents the optimization from breaking requests
    when the language cache wasn't initialized correctly.
    """

    if not language_name:

        return None

    normalized_name = (
        language_name.strip().lower()
    )

    # --------------------------------------------------------
    # 1. FAST PATH
    # --------------------------------------------------------

    with _language_cache_lock:

        cached_code = _language_cache.get(
            normalized_name
        )

    if cached_code:

        return cached_code

    # --------------------------------------------------------
    # 2. CACHE MISS
    # --------------------------------------------------------

    if not endpoint or not api_key:

        logging.error(
            "Language cache miss for '%s', "
            "but Translator configuration is unavailable.",
            language_name
        )

        return None

    try:

        logging.warning(
            "Language cache miss for '%s'. "
            "Refreshing supported languages.",
            language_name
        )

        supported_languages = (
            get_supported_languages(
                endpoint,
                api_key
            )
        )

        build_language_cache(
            supported_languages
        )

        # ----------------------------------------------------
        # 3. RETRY FROM REFRESHED CACHE
        # ----------------------------------------------------

        with _language_cache_lock:

            return _language_cache.get(
                normalized_name
            )

    except Exception:

        logging.exception(
            "Failed to refresh language cache "
            "for language '%s'.",
            language_name
        )

        return None


# ============================================================
# APPLICATION INITIALIZATION
# ============================================================

def initialize_application():

    try:

        initialize_db_pool()

        # ----------------------------------------------------
        # Load DB settings and cache them
        # ----------------------------------------------------

        settings = fetch_settings(
            ADMIN_ID
        )

        if settings is None:

            logging.warning(
                "Application started without database settings."
            )

            return

        key, endpoint, region = settings

        # ----------------------------------------------------
        # Load supported languages ONCE
        # ----------------------------------------------------

        try:

            supported_languages = (
                get_supported_languages(
                    endpoint,
                    key
                )
            )

            build_language_cache(
                supported_languages
            )

        except Exception:

            logging.exception(
                "Initial language cache load failed. "
                "The first language lookup can retry."
            )

        logging.info(
            "Application initialization completed."
        )

    except Exception:

        logging.exception(
            "Application initialization encountered an error."
        )


# ============================================================
# TRANSLATION ENDPOINT
# ============================================================

@app.route(
    "/text_trans_azure",
    methods=["POST"]
)
def text_trans_azure():

    logging.info(
        "Processing translation request."
    )

    # --------------------------------------------------------
    # Hardcoded Admin ID
    # --------------------------------------------------------

    admin_id = ADMIN_ID

    # --------------------------------------------------------
    # Get settings
    #
    # Cached normally.
    # DB fallback only if cache is empty.
    # --------------------------------------------------------

    result = fetch_settings(
        admin_id
    )

    if result is None or len(result) < 3:

        logging.error(
            "Failed to retrieve all required settings "
            "(key, text_translation_endpoint, region)."
        )

        return jsonify({
            "error": (
                "Failed to retrieve all required settings "
                "(key, text_translation_endpoint, region)."
            )
        }), 500

    # --------------------------------------------------------
    # Unpack settings
    # --------------------------------------------------------

    key, text_translation_endpoint, region = result

    # --------------------------------------------------------
    # Request data
    # --------------------------------------------------------

    data = request.get_json(
        silent=True
    )

    if not data:

        return jsonify({
            "error": (
                "Please pass target_language and text "
                "in the request."
            )
        }), 400

    target_language_name = data.get(
        "target_language"
    )

    source_language_name = data.get(
        "source_language"
    )

    text_to_translate = data.get(
        "text"
    )

    # --------------------------------------------------------
    # Validate
    # --------------------------------------------------------

    if not target_language_name or not text_to_translate:

        return jsonify({
            "error": (
                "Please pass target_language and text "
                "in the request."
            )
        }), 400

    # --------------------------------------------------------
    # TARGET LANGUAGE
    #
    # Cache first.
    # /languages fallback only on cache miss.
    # --------------------------------------------------------

    target_language_code = (
        get_language_code(
            target_language_name,
            endpoint=text_translation_endpoint,
            api_key=key
        )
    )

    if not target_language_code:

        return jsonify({
            "error": (
                f"Target language "
                f"'{target_language_name}' "
                "is not supported."
            )
        }), 400

    # --------------------------------------------------------
    # SOURCE LANGUAGE
    # --------------------------------------------------------

    source_language_code = None

    if source_language_name:

        source_language_code = (
            get_language_code(
                source_language_name,
                endpoint=text_translation_endpoint,
                api_key=key
            )
        )

        if not source_language_code:

            return jsonify({
                "error": (
                    f"Source language "
                    f"'{source_language_name}' "
                    "is not supported."
                )
            }), 400

    # --------------------------------------------------------
    # AZURE TRANSLATOR API
    # --------------------------------------------------------

    path = "/translate"

    constructed_url = (
        f"{text_translation_endpoint.rstrip('/')}"
        f"{path}"
    )

    params = {
        "api-version": "3.0",
        "to": [target_language_code]
    }

    if source_language_code:

        params["from"] = (
            source_language_code
        )

    request_id = str(
        uuid.uuid4()
    )

    headers = {
        "Ocp-Apim-Subscription-Key": key,
        "Ocp-Apim-Subscription-Region": region,
        "Content-Type": "application/json",
        "X-ClientTraceId": request_id
    }

    body = [
        {
            "text": text_to_translate
        }
    ]

    try:

        # ----------------------------------------------------
        # Reusable HTTP connection
        # ----------------------------------------------------

        response = http_session.post(
            constructed_url,
            params=params,
            headers=headers,
            json=body,
            timeout=HTTP_TIMEOUT
        )

        # ----------------------------------------------------
        # DETAILED AZURE ERROR
        #
        # ONLY CHANGE FROM PREVIOUS VERSION:
        # return the actual Azure status code.
        # ----------------------------------------------------

        if not response.ok:

            logging.error(
                (
                    "TRANSLATOR FAILURE | "
                    "RequestID=%s | "
                    "HTTPStatus=%s | "
                    "Response=%s"
                ),
                request_id,
                response.status_code,
                response.text[:4000]
            )

            try:

                error_body = response.json()

            except ValueError:

                error_body = {
                    "message": response.text[:4000]
                }

            return jsonify({
                "error": "Azure Translator request failed.",
                "downstream_status": response.status_code,
                "downstream_response": error_body,
                "request_id": request_id
            }), response.status_code

        # ----------------------------------------------------
        # SUCCESS
        # ----------------------------------------------------

        response_json = response.json()

        return jsonify(
            response_json
        ), 200

    except requests.exceptions.Timeout as timeout_err:

        logging.error(
            (
                "TRANSLATOR TIMEOUT | "
                "RequestID=%s | "
                "Error=%s"
            ),
            request_id,
            str(timeout_err),
            exc_info=True
        )

        return jsonify({
            "error": (
                "Translation service request timed out."
            )
        }), 504

    except requests.exceptions.HTTPError as http_err:

        logging.error(
            (
                "HTTP error occurred | "
                "RequestID=%s | "
                "Error=%s"
            ),
            request_id,
            str(http_err)
        )

        return jsonify({
            "error": (
                f"HTTP error occurred: "
                f"{http_err}"
            )
        }), 500

    except requests.exceptions.RequestException as req_err:

        logging.error(
            (
                "Request error occurred | "
                "RequestID=%s | "
                "Error=%s"
            ),
            request_id,
            str(req_err),
            exc_info=True
        )

        return jsonify({
            "error": (
                f"Request error occurred: "
                f"{req_err}"
            )
        }), 500

    except Exception as e:

        logging.error(
            (
                "Unexpected translation error | "
                "RequestID=%s | "
                "Error=%s"
            ),
            request_id,
            str(e),
            exc_info=True
        )

        return jsonify({
            "error": (
                "An unexpected error occurred "
                "while processing the translation."
            )
        }), 500


# ============================================================
# START APPLICATION
# ============================================================

if __name__ == "__main__":

    initialize_application()

    app.run(
        host="0.0.0.0",
        port=int(
            os.getenv(
                "PORT",
                "5000"
            )
        ),
        debug=False,
        threaded=True
    )
