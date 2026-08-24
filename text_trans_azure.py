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
from collections import defaultdict
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

DB_POOL_MIN = int(os.getenv("DB_POOL_MIN", "2"))
DB_POOL_MAX = int(os.getenv("DB_POOL_MAX", "20"))


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
# BATCH CONFIGURATION
# ============================================================

# Existing requests remain single-request unless explicitly:
#
#     "batch": true
#
BATCH_ENABLED_DEFAULT = False


# Safe batch size.
#
# Azure Translator supports multiple texts in one request.
# We intentionally stay below the maximum to leave safety margin.
BATCH_MAX_ITEMS = int(
    os.getenv(
        "TRANSLATOR_BATCH_MAX_ITEMS",
        "50"
    )
)


# Keep character count comfortably below the downstream limit.
BATCH_MAX_CHARACTERS = int(
    os.getenv(
        "TRANSLATOR_BATCH_MAX_CHARACTERS",
        "40000"
    )
)


# Maximum time the collector waits for additional compatible
# requests before flushing the current batch.
BATCH_MAX_WAIT_SECONDS = float(
    os.getenv(
        "TRANSLATOR_BATCH_MAX_WAIT_SECONDS",
        "0.05"
    )
)


# Number of Azure Translator requests allowed simultaneously.
#
# IMPORTANT:
# This is deliberately controlled instead of allowing every
# incoming HTTP request to independently hit Translator.
BATCH_DISPATCH_CONCURRENCY = int(
    os.getenv(
        "TRANSLATOR_BATCH_DISPATCH_CONCURRENCY",
        "2"
    )
)


# Number of retries specifically for Azure 429.
BATCH_429_RETRIES = int(
    os.getenv(
        "TRANSLATOR_429_RETRIES",
        "5"
    )
)


# Base backoff when Azure returns 429 and no Retry-After is supplied.
BATCH_429_BACKOFF_SECONDS = float(
    os.getenv(
        "TRANSLATOR_429_BACKOFF_SECONDS",
        "1.0"
    )
)


# Maximum time an individual incoming request is allowed to wait
# for the batch operation.
#
# Keep this higher than the load-test timeout if possible.
BATCH_REQUEST_TIMEOUT = float(
    os.getenv(
        "TRANSLATOR_BATCH_REQUEST_TIMEOUT",
        "120"
    )
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
    # FAST PATH
    # --------------------------------------------------------

    with _settings_lock:

        if _settings_cache is not None:
            return _settings_cache

    # --------------------------------------------------------
    # CACHE EMPTY
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
        # CACHE
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

_language_refresh_lock = threading.Lock()


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

    if not language_name:
        return None

    normalized_name = (
        language_name.strip().lower()
    )

    # --------------------------------------------------------
    # FAST CACHE LOOKUP
    # --------------------------------------------------------

    with _language_cache_lock:

        cached_code = _language_cache.get(
            normalized_name
        )

    if cached_code:
        return cached_code

    # --------------------------------------------------------
    # CACHE MISS
    # --------------------------------------------------------

    if not endpoint or not api_key:

        logging.error(
            "Language cache miss for '%s', "
            "but Translator configuration is unavailable.",
            language_name
        )

        return None

    # Prevent 1000 simultaneous requests from all trying
    # to refresh /languages at the same time.
    with _language_refresh_lock:

        # Another request may have populated it while
        # this request was waiting for the lock.
        with _language_cache_lock:

            cached_code = _language_cache.get(
                normalized_name
            )

        if cached_code:
            return cached_code

        try:

            logging.info(
                "Refreshing language cache for '%s'.",
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
# BATCH REQUEST OBJECT
# ============================================================

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


# ============================================================
# TRANSLATION BATCHER
# ============================================================

class TranslationBatcher:

    def __init__(self):

        # ----------------------------------------------------
        # Incoming requests
        # ----------------------------------------------------

        self.input_queue = Queue()

        # ----------------------------------------------------
        # Batches waiting to be sent to Azure
        # ----------------------------------------------------

        self.batch_queue = Queue()

        # ----------------------------------------------------
        # Collector
        # ----------------------------------------------------

        self.collector = threading.Thread(
            target=self._collector_loop,
            daemon=True,
            name="translator-batch-collector"
        )

        self.collector.start()

        # ----------------------------------------------------
        # Azure dispatch workers
        # ----------------------------------------------------

        self.dispatchers = []

        for index in range(
            BATCH_DISPATCH_CONCURRENCY
        ):

            worker = threading.Thread(
                target=self._dispatcher_loop,
                daemon=True,
                name=f"translator-batch-dispatcher-{index + 1}"
            )

            worker.start()

            self.dispatchers.append(
                worker
            )

        logging.info(
            "Translator batch system started. "
            "max_items=%s max_chars=%s max_wait=%ss "
            "dispatch_concurrency=%s",
            BATCH_MAX_ITEMS,
            BATCH_MAX_CHARACTERS,
            BATCH_MAX_WAIT_SECONDS,
            BATCH_DISPATCH_CONCURRENCY
        )

    # ========================================================
    # SUBMIT
    # ========================================================

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

        self.input_queue.put(
            item
        )

        return item

    # ========================================================
    # COLLECTOR
    # ========================================================

    def _collector_loop(self):

        while True:

            try:

                first_item = (
                    self.input_queue.get()
                )

                batch = [
                    first_item
                ]

                total_characters = len(
                    first_item.text
                )

                batch_start = time.monotonic()

                # ------------------------------------------------
                # Collect compatible requests.
                #
                # We stop when:
                #
                # 1. max items reached
                # 2. max characters reached
                # 3. max wait reached
                # ------------------------------------------------

                while (
                    len(batch)
                    < BATCH_MAX_ITEMS
                    and total_characters
                    < BATCH_MAX_CHARACTERS
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

                        candidate = (
                            self.input_queue.get(
                                timeout=remaining_wait
                            )
                        )

                    except Empty:

                        break

                    same_source = (
                        candidate.source_language_code
                        ==
                        first_item.source_language_code
                    )

                    same_target = (
                        candidate.target_language_code
                        ==
                        first_item.target_language_code
                    )

                    candidate_size = len(
                        candidate.text
                    )

                    # ------------------------------------------------
                    # Add compatible item.
                    # ------------------------------------------------

                    if (
                        same_source
                        and same_target
                        and (
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

                        # Different language pair.
                        #
                        # Put it back into the queue.
                        self.input_queue.put(
                            candidate
                        )

                        break

                # ------------------------------------------------
                # Put completed batch into dispatcher queue.
                #
                # IMPORTANT:
                # The collector does NOT call Azure.
                # This prevents incoming HTTP traffic from
                # directly controlling Azure concurrency.
                # ------------------------------------------------

                self.batch_queue.put(
                    batch
                )

                logging.info(
                    "BATCH CREATED | "
                    "Items=%s | "
                    "Characters=%s | "
                    "QueueDepth=%s",
                    len(batch),
                    total_characters,
                    self.batch_queue.qsize()
                )

            except Exception:

                logging.exception(
                    "Unexpected error in batch collector."
                )

    # ========================================================
    # DISPATCHER
    # ========================================================

    def _dispatcher_loop(self):

        while True:

            try:

                batch = self.batch_queue.get()

                self._process_batch(
                    batch
                )

            except Exception:

                logging.exception(
                    "Unexpected error in batch dispatcher."
                )

    # ========================================================
    # PROCESS BATCH
    # ========================================================

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
            # Settings are cached.
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
                        "Translation service "
                        "configuration is temporarily "
                        "unavailable."
                    ),
                    "request_id": request_id
                }

                for item in batch:

                    item.error_status = 503

                    item.error_body = (
                        error_body
                    )

                    item.request_id = (
                        request_id
                    )

                    item.event.set()

                return

            key, endpoint, region = settings

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

            body = [
                {
                    "text": item.text
                }
                for item in batch
            ]

            total_characters = sum(
                len(item.text)
                for item in batch
            )

            # ----------------------------------------------------
            # SEND WITH 429 RETRY/BACKOFF
            # ----------------------------------------------------

            response = None

            for attempt in range(
                BATCH_429_RETRIES + 1
            ):

                logging.info(
                    "TRANSLATOR BATCH SEND | "
                    "RequestID=%s | "
                    "BatchSize=%s | "
                    "Characters=%s | "
                    "Attempt=%s",
                    request_id,
                    len(batch),
                    total_characters,
                    attempt + 1
                )

                try:

                    response = (
                        http_session.post(
                            constructed_url,
                            params=params,
                            headers=headers,
                            json=body,
                            timeout=HTTP_TIMEOUT
                        )
                    )

                except requests.exceptions.Timeout:

                    if attempt < BATCH_429_RETRIES:

                        backoff = (
                            BATCH_429_BACKOFF_SECONDS
                            * (2 ** attempt)
                        )

                        logging.warning(
                            "TRANSLATOR TIMEOUT | "
                            "RequestID=%s | "
                            "retrying in %.2fs",
                            request_id,
                            backoff
                        )

                        time.sleep(
                            backoff
                        )

                        continue

                    raise

                # ------------------------------------------------
                # SUCCESS
                # ------------------------------------------------

                if response.status_code == 200:
                    break

                # ------------------------------------------------
                # AZURE RATE LIMIT
                # ------------------------------------------------

                if response.status_code == 429:

                    if attempt >= BATCH_429_RETRIES:
                        break

                    retry_after = (
                        response.headers.get(
                            "Retry-After"
                        )
                    )

                    if retry_after:

                        try:
                            backoff = float(
                                retry_after
                            )
                        except ValueError:
                            backoff = (
                                BATCH_429_BACKOFF_SECONDS
                                * (2 ** attempt)
                            )

                    else:

                        backoff = (
                            BATCH_429_BACKOFF_SECONDS
                            * (2 ** attempt)
                        )

                    logging.warning(
                        "AZURE 429 | "
                        "RequestID=%s | "
                        "BatchSize=%s | "
                        "Attempt=%s | "
                        "RetryingIn=%.2fs | "
                        "AzureResponse=%s",
                        request_id,
                        len(batch),
                        attempt + 1,
                        backoff,
                        response.text[:1000]
                    )

                    time.sleep(
                        backoff
                    )

                    continue

                # ------------------------------------------------
                # Other HTTP errors.
                #
                # Do NOT retry blindly.
                # ------------------------------------------------

                break

            # ====================================================
            # DOWNSTREAM FAILURE
            # ====================================================

            if response is None:

                raise RuntimeError(
                    "No response received from Translator."
                )

            if not response.ok:

                logging.error(
                    "TRANSLATOR BATCH FAILURE | "
                    "RequestID=%s | "
                    "BatchSize=%s | "
                    "HTTPStatus=%s | "
                    "Response=%s",
                    request_id,
                    len(batch),
                    response.status_code,
                    response.text[:4000]
                )

                try:

                    downstream_body = (
                        response.json()
                    )

                except ValueError:

                    downstream_body = {
                        "message":
                            response.text[:4000]
                    }

                error_body = {
                    "error": (
                        "Azure Translator "
                        "request failed."
                    ),
                    "downstream_status":
                        response.status_code,
                    "downstream_response":
                        downstream_body,
                    "request_id":
                        request_id
                }

                for item in batch:

                    item.error_status = (
                        response.status_code
                    )

                    item.error_body = (
                        error_body
                    )

                    item.request_id = (
                        request_id
                    )

                    item.event.set()

                return

            # ====================================================
            # PARSE SUCCESS
            # ====================================================

            response_json = response.json()

            if (
                not isinstance(
                    response_json,
                    list
                )
                or
                len(response_json)
                != len(batch)
            ):

                logging.error(
                    "Unexpected Translator batch response | "
                    "RequestID=%s | "
                    "Expected=%s | "
                    "Received=%s",
                    request_id,
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
                        "Unexpected response "
                        "received from Azure "
                        "Translator."
                    ),
                    "request_id":
                        request_id
                }

                for item in batch:

                    item.error_status = 502

                    item.error_body = (
                        error_body
                    )

                    item.request_id = (
                        request_id
                    )

                    item.event.set()

                return

            # ====================================================
            # MAP RESULTS
            # ====================================================

            for index, item in enumerate(
                batch
            ):

                item.result = (
                    response_json[index]
                )

                item.request_id = (
                    request_id
                )

                item.event.set()

            logging.info(
                "TRANSLATOR BATCH SUCCESS | "
                "RequestID=%s | "
                "Items=%s | "
                "Characters=%s",
                request_id,
                len(batch),
                total_characters
            )

        except requests.exceptions.Timeout as e:

            logging.error(
                "TRANSLATOR BATCH TIMEOUT | "
                "RequestID=%s | "
                "BatchSize=%s | "
                "Error=%s",
                request_id,
                len(batch),
                str(e),
                exc_info=True
            )

            error_body = {
                "error": (
                    "Translation service "
                    "request timed out."
                ),
                "request_id":
                    request_id
            }

            for item in batch:

                item.error_status = 504

                item.error_body = (
                    error_body
                )

                item.request_id = (
                    request_id
                )

                item.event.set()

        except requests.exceptions.RequestException as e:

            logging.error(
                "TRANSLATOR REQUEST ERROR | "
                "RequestID=%s | "
                "BatchSize=%s | "
                "Error=%s",
                request_id,
                len(batch),
                str(e),
                exc_info=True
            )

            error_body = {
                "error": (
                    "Translator request "
                    "could not be completed."
                ),
                "details": str(e),
                "request_id":
                    request_id
            }

            for item in batch:

                item.error_status = 502

                item.error_body = (
                    error_body
                )

                item.request_id = (
                    request_id
                )

                item.event.set()

        except Exception as e:

            logging.error(
                "UNEXPECTED BATCH ERROR | "
                "RequestID=%s | "
                "BatchSize=%s | "
                "Error=%s",
                request_id,
                len(batch),
                str(e),
                exc_info=True
            )

            error_body = {
                "error": (
                    "An unexpected error "
                    "occurred while processing "
                    "the translation."
                ),
                "details": str(e),
                "request_id":
                    request_id
            }

            for item in batch:

                item.error_status = 500

                item.error_body = (
                    error_body
                )

                item.request_id = (
                    request_id
                )

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

        settings = fetch_settings(
            ADMIN_ID
        )

        if settings is None:

            logging.warning(
                "Application started without "
                "database settings."
            )

            return

        key, endpoint, region = settings

        # ----------------------------------------------------
        # Load language mappings once.
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
            "Application initialization "
            "encountered an error."
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

    admin_id = ADMIN_ID

    # --------------------------------------------------------
    # Cached settings.
    # --------------------------------------------------------

    result = fetch_settings(
        admin_id
    )

    if result is None or len(result) < 3:

        return jsonify({
            "error": (
                "Translation service "
                "configuration is temporarily "
                "unavailable."
            )
        }), 503

    key, text_translation_endpoint, region = result

    # --------------------------------------------------------
    # Request body
    # --------------------------------------------------------

    data = request.get_json(
        silent=True
    )

    if not data:

        return jsonify({
            "error": (
                "Please pass target_language "
                "and text in the request."
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
    # Batch flag
    # --------------------------------------------------------

    batch_requested = data.get(
        "batch",
        BATCH_ENABLED_DEFAULT
    )

    batch_requested = (
        batch_requested is True
    )

    # --------------------------------------------------------
    # Validation
    # --------------------------------------------------------

    if (
        not target_language_name
        or not text_to_translate
    ):

        return jsonify({
            "error": (
                "Please pass target_language "
                "and text in the request."
            )
        }), 400

    # ========================================================
    # LANGUAGE RESOLUTION
    # ========================================================

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
    # BATCH PATH
    # ========================================================

    if batch_requested:

        logging.info(
            "BATCH REQUEST RECEIVED | "
            "Source=%s | "
            "Target=%s | "
            "Characters=%s | "
            "QueueDepth=%s",
            source_language_code,
            target_language_code,
            len(text_to_translate),
            translation_batcher.input_queue.qsize()
        )

        batch_item = (
            translation_batcher.submit(
                text=text_to_translate,
                source_language_code=
                    source_language_code,
                target_language_code=
                    target_language_code
            )
        )

        # ----------------------------------------------------
        # Wait for THIS request's result.
        #
        # The request is not calling Azure directly.
        # The batch worker does it.
        # ----------------------------------------------------

        completed = (
            batch_item.event.wait(
                timeout=BATCH_REQUEST_TIMEOUT
            )
        )

        if not completed:

            request_id = str(
                uuid.uuid4()
            )

            logging.error(
                "BATCH REQUEST TIMEOUT | "
                "RequestID=%s | "
                "QueueDepth=%s",
                request_id,
                translation_batcher.input_queue.qsize()
            )

            return jsonify({
                "error": (
                    "Translation request "
                    "remained queued beyond "
                    "the allowed processing time."
                ),
                "request_id":
                    request_id
            }), 504

        # ----------------------------------------------------
        # Batch failed.
        # ----------------------------------------------------

        if batch_item.error_status is not None:

            return jsonify(
                batch_item.error_body
            ), batch_item.error_status

        # ----------------------------------------------------
        # Return this request's result.
        # ----------------------------------------------------

        return jsonify(
            batch_item.result
        ), 200

    # ========================================================
    # EXISTING SINGLE REQUEST PATH
    # ========================================================

    path = "/translate"

    constructed_url = (
        f"{text_translation_endpoint.rstrip('/')}"
        f"{path}"
    )

    params = {
        "api-version": "3.0",
        "to": [
            target_language_code
        ]
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

        response = (
            http_session.post(
                constructed_url,
                params=params,
                headers=headers,
                json=body,
                timeout=HTTP_TIMEOUT
            )
        )

        # ----------------------------------------------------
        # Return exact downstream status/error.
        # ----------------------------------------------------

        if not response.ok:

            logging.error(
                "TRANSLATOR FAILURE | "
                "RequestID=%s | "
                "HTTPStatus=%s | "
                "Response=%s",
                request_id,
                response.status_code,
                response.text[:4000]
            )

            try:

                error_body = (
                    response.json()
                )

            except ValueError:

                error_body = {
                    "message":
                        response.text[:4000]
                }

            return jsonify({
                "error": (
                    "Azure Translator "
                    "request failed."
                ),
                "downstream_status":
                    response.status_code,
                "downstream_response":
                    error_body,
                "request_id":
                    request_id
            }), response.status_code

        response_json = (
            response.json()
        )

        return jsonify(
            response_json
        ), 200

    except requests.exceptions.Timeout:

        return jsonify({
            "error": (
                "Translation service "
                "request timed out."
            ),
            "request_id":
                request_id
        }), 504

    except requests.exceptions.RequestException as e:

        logging.error(
            "Translator request error | "
            "RequestID=%s | Error=%s",
            request_id,
            str(e),
            exc_info=True
        )

        return jsonify({
            "error": (
                "Translator request "
                "could not be completed."
            ),
            "details": str(e),
            "request_id":
                request_id
        }), 502

    except Exception as e:

        logging.error(
            "Unexpected translation error | "
            "RequestID=%s | Error=%s",
            request_id,
            str(e),
            exc_info=True
        )

        return jsonify({
            "error": (
                "An unexpected error occurred "
                "while processing the translation."
            ),
            "details": str(e),
            "request_id":
                request_id
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
