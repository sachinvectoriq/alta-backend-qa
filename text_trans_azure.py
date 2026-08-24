from flask import Flask, request, jsonify
import logging
import requests
import uuid
import psycopg2
import os
import threading
import time
from dataclasses import dataclass
from queue import Queue, Empty

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
        cache miss -> refresh supported languages -> retry
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
# BATCH TRANSLATION
#
# OPT-IN ONLY
#
# Normal requests are NOT affected.
#
# Request:
# {
#     "text": "...",
#     "source_language": "English",
#     "target_language": "French",
#     "batch": true
# }
#
# ============================================================

BATCH_ENABLED_DEFAULT = False

BATCH_MAX_ITEMS = int(
    os.getenv(
        "TRANSLATOR_BATCH_MAX_ITEMS",
        "60"
    )
)

BATCH_MAX_CHARACTERS = int(
    os.getenv(
        "TRANSLATOR_BATCH_MAX_CHARACTERS",
        "45000"
    )
)

BATCH_MAX_WAIT_SECONDS = float(
    os.getenv(
        "TRANSLATOR_BATCH_MAX_WAIT_SECONDS",
        "0.10"
    )
)


@dataclass
class BatchRequest:

    text: str
    source_language_code: str | None
    target_language_code: str

    event: threading.Event

    result: object = None
    error_status: int | None = None
    error_body: object = None
    request_id: str | None = None


class TranslationBatcher:

    def __init__(self):

        self.queue = Queue()

        self.worker = threading.Thread(
            target=self._worker_loop,
            daemon=True,
            name="translator-batch-worker"
        )

        self.worker.start()

        logging.info(
            "Translator batch worker started. "
            "max_items=%s max_characters=%s max_wait=%ss",
            BATCH_MAX_ITEMS,
            BATCH_MAX_CHARACTERS,
            BATCH_MAX_WAIT_SECONDS
        )

    def submit(
        self,
        text,
        source_language_code,
        target_language_code
    ):

        item = BatchRequest(
            text=text,
            source_language_code=source_language_code,
            target_language_code=target_language_code,
            event=threading.Event()
        )

        self.queue.put(item)

        return item

    def _worker_loop(self):

        while True:

            try:

                first_item = self.queue.get()

                batch = [
                    first_item
                ]

                total_characters = len(
                    first_item.text
                )

                batch_start = time.monotonic()

                # ------------------------------------------------
                # Collect compatible requests
                # ------------------------------------------------

                while (
                    len(batch) < BATCH_MAX_ITEMS
                    and total_characters < BATCH_MAX_CHARACTERS
                ):

                    remaining_wait = (
                        BATCH_MAX_WAIT_SECONDS
                        - (
                            time.monotonic()
                            - batch_start
                        )
                    )

                    if remaining_wait <= 0:
                        break

                    try:

                        candidate = self.queue.get(
                            timeout=remaining_wait
                        )

                    except Empty:

                        break

                    # ------------------------------------------------
                    # IMPORTANT:
                    #
                    # Requests with different source/target languages
                    # cannot be placed in the same Translator request.
                    # ------------------------------------------------

                    same_source = (
                        candidate.source_language_code
                        == first_item.source_language_code
                    )

                    same_target = (
                        candidate.target_language_code
                        == first_item.target_language_code
                    )

                    candidate_size = len(
                        candidate.text
                    )

                    if (
                        same_source
                        and same_target
                        and
                        (
                            total_characters
                            + candidate_size
                            <= BATCH_MAX_CHARACTERS
                        )
                    ):

                        batch.append(
                            candidate
                        )

                        total_characters += (
                            candidate_size
                        )

                    else:

                        # ------------------------------------------------
                        # Not compatible with this batch.
                        #
                        # Put it back so another batch can process it.
                        # ------------------------------------------------

                        self.queue.put(
                            candidate
                        )

                        break

                # ------------------------------------------------
                # Send batch
                # ------------------------------------------------

                self._process_batch(
                    batch
                )

            except Exception:

                logging.exception(
                    "Unexpected error in batch worker."
                )


    def _process_batch(
        self,
        batch
    ):

        if not batch:
            return

        first = batch[0]

        request_id = str(
            uuid.uuid4()
        )

        try:

            # ----------------------------------------------------
            # Settings are already cached by the API layer.
            # ----------------------------------------------------

            settings = fetch_settings(
                ADMIN_ID
            )

            if (
                settings is None
                or len(settings) < 3
            ):

                error_body = {
                    "error": (
                        "Failed to retrieve all required "
                        "settings."
                    )
                }

                for item in batch:

                    item.error_status = 500
                    item.error_body = error_body
                    item.request_id = request_id
                    item.event.set()

                return

            key, endpoint, region = settings

            # ----------------------------------------------------
            # Translator endpoint
            # ----------------------------------------------------

            constructed_url = (
                f"{endpoint.rstrip('/')}"
                "/translate"
            )

            params = {
                "api-version": "3.0",
                "to": [
                    first.target_language_code
                ]
            }

            if first.source_language_code:

                params["from"] = (
                    first.source_language_code
                )

            headers = {
                "Ocp-Apim-Subscription-Key": key,
                "Ocp-Apim-Subscription-Region": region,
                "Content-Type": "application/json",
                "X-ClientTraceId": request_id
            }

            # ----------------------------------------------------
            # THIS IS THE MAIN BATCH OPTIMIZATION
            #
            # Instead of:
            #
            #   POST -> one text
            #   POST -> one text
            #   POST -> one text
            #
            # We send:
            #
            #   POST -> [text1, text2, text3, ...]
            # ----------------------------------------------------

            body = [
                {
                    "text": item.text
                }
                for item in batch
            ]

            logging.info(
                "TRANSLATOR BATCH | "
                "BatchSize=%s | "
                "Characters=%s | "
                "Source=%s | "
                "Target=%s | "
                "RequestID=%s",
                len(batch),
                sum(len(item.text) for item in batch),
                first.source_language_code,
                first.target_language_code,
                request_id
            )

            response = http_session.post(
                constructed_url,
                params=params,
                headers=headers,
                json=body,
                timeout=HTTP_TIMEOUT
            )

            # ----------------------------------------------------
            # EXACT AZURE ERROR
            # ----------------------------------------------------

            if not response.ok:

                logging.error(
                    (
                        "TRANSLATOR BATCH FAILURE | "
                        "RequestID=%s | "
                        "BatchSize=%s | "
                        "HTTPStatus=%s | "
                        "Response=%s"
                    ),
                    request_id,
                    len(batch),
                    response.status_code,
                    response.text[:4000]
                )

                try:

                    error_body = response.json()

                except ValueError:

                    error_body = {
                        "message": response.text[:4000]
                    }

                for item in batch:

                    item.error_status = (
                        response.status_code
                    )

                    item.error_body = {
                        "error": (
                            "Azure Translator batch "
                            "request failed."
                        ),
                        "downstream_status": (
                            response.status_code
                        ),
                        "downstream_response": (
                            error_body
                        ),
                        "request_id": request_id
                    }

                    item.request_id = request_id

                    item.event.set()

                return

            # ----------------------------------------------------
            # SUCCESS
            # ----------------------------------------------------

            response_json = response.json()

            # Azure returns translations in the same order
            # as the input array.
            if (
                not isinstance(response_json, list)
                or len(response_json) != len(batch)
            ):

                logging.error(
                    "Unexpected Translator batch response. "
                    "Expected %s results, received %s.",
                    len(batch),
                    (
                        len(response_json)
                        if isinstance(
                            response_json,
                            list
                        )
                        else "non-list"
                    )
                )

                error_body = {
                    "error": (
                        "Unexpected response received "
                        "from Azure Translator."
                    ),
                    "request_id": request_id
                }

                for item in batch:

                    item.error_status = 502
                    item.error_body = error_body
                    item.request_id = request_id
                    item.event.set()

                return

            # ----------------------------------------------------
            # MAP EACH AZURE RESULT BACK TO ITS ORIGINAL REQUEST
            # ----------------------------------------------------

            for index, item in enumerate(batch):

                item.result = (
                    response_json[index]
                )

                item.request_id = request_id

                item.event.set()

        except requests.exceptions.Timeout as timeout_err:

            logging.error(
                (
                    "TRANSLATOR BATCH TIMEOUT | "
                    "RequestID=%s | "
                    "BatchSize=%s | "
                    "Error=%s"
                ),
                request_id,
                len(batch),
                str(timeout_err),
                exc_info=True
            )

            for item in batch:

                item.error_status = 504

                item.error_body = {
                    "error": (
                        "Translation service "
                        "request timed out."
                    ),
                    "request_id": request_id
                }

                item.request_id = request_id

                item.event.set()

        except requests.exceptions.RequestException as req_err:

            logging.error(
                (
                    "TRANSLATOR BATCH REQUEST ERROR | "
                    "RequestID=%s | "
                    "BatchSize=%s | "
                    "Error=%s"
                ),
                request_id,
                len(batch),
                str(req_err),
                exc_info=True
            )

            for item in batch:

                item.error_status = 500

                item.error_body = {
                    "error": (
                        f"Request error occurred: "
                        f"{req_err}"
                    ),
                    "request_id": request_id
                }

                item.request_id = request_id

                item.event.set()

        except Exception as e:

            logging.error(
                (
                    "UNEXPECTED BATCH ERROR | "
                    "RequestID=%s | "
                    "BatchSize=%s | "
                    "Error=%s"
                ),
                request_id,
                len(batch),
                str(e),
                exc_info=True
            )

            for item in batch:

                item.error_status = 500

                item.error_body = {
                    "error": (
                        "An unexpected error occurred "
                        "while processing the translation."
                    ),
                    "request_id": request_id
                }

                item.request_id = request_id

                item.event.set()


# ============================================================
# GLOBAL BATCHER
# ============================================================

translation_batcher = TranslationBatcher()


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
    # NEW:
    # BATCH FLAG
    #
    # If omitted or false:
    # existing behavior.
    #
    # If true:
    # request enters batch collector.
    # --------------------------------------------------------

    batch_requested = data.get(
        "batch",
        BATCH_ENABLED_DEFAULT
    )

    # Make sure only an explicit true enables batching.
    batch_requested = (
        batch_requested is True
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

    # ========================================================
    # NEW BATCH PATH
    #
    # ONLY runs when:
    #
    #     "batch": true
    #
    # ========================================================

    if batch_requested:

        logging.info(
            "BATCH REQUEST | "
            "Source=%s | "
            "Target=%s | "
            "Characters=%s",
            source_language_code,
            target_language_code,
            len(text_to_translate)
        )

        batch_item = translation_batcher.submit(
            text=text_to_translate,
            source_language_code=source_language_code,
            target_language_code=target_language_code
        )

        # ----------------------------------------------------
        # Wait for the batch worker to process this request.
        #
        # The worker waits up to BATCH_MAX_WAIT_SECONDS
        # to collect compatible requests.
        # ----------------------------------------------------

        batch_item.event.wait()

        # ----------------------------------------------------
        # Batch failed
        # ----------------------------------------------------

        if batch_item.error_status is not None:

            return jsonify(
                batch_item.error_body
            ), batch_item.error_status

        # ----------------------------------------------------
        # Batch succeeded
        #
        # Return ONLY this request's Azure result.
        # ----------------------------------------------------

        return jsonify(
            batch_item.result
        ), 200

    # ========================================================
    # EXISTING SINGLE-REQUEST PATH
    #
    # UNCHANGED.
    #
    # ========================================================

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
