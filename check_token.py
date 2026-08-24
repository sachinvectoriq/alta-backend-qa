from flask import Flask, request, jsonify
import tiktoken
import json
import os
import socket
import sys
import traceback
import time
from fetch_token_limit import get_token_limit  # ← direct import, no self-call

app = Flask(__name__)

DEFAULT_MODEL = "gpt-4o"


# =========================
# TOKEN COUNT FUNCTION
# =========================
def count_tokens(text, model_name=DEFAULT_MODEL):
    print("[DEBUG] Entered count_tokens()", flush=True)

    try:
        print(f"[DEBUG] Model selected: {model_name}", flush=True)
        encoding = tiktoken.encoding_for_model(model_name)
        print("[DEBUG] Encoding loaded successfully", flush=True)

    except Exception as e:
        print("[ERROR] encoding_for_model FAILED", flush=True)
        print(traceback.format_exc(), flush=True)
        print("[WARN] Falling back to cl100k_base", flush=True)
        encoding = tiktoken.get_encoding("cl100k_base")

    try:
        print(f"[DEBUG] Encoding text type: {type(text)}", flush=True)
        print(f"[DEBUG] Encoding text preview: {str(text)[:100]}", flush=True)

        result = encoding.encode(text)

        print("[DEBUG] Encoding SUCCESS", flush=True)
        print(f"[DEBUG] Token count result: {len(result)}", flush=True)

        return len(result)

    except Exception as e:
        print("[ERROR] encoding.encode() FAILED", flush=True)
        print(traceback.format_exc(), flush=True)
        raise


# =========================
# MAIN API
# =========================
@app.route('/check_token_count', methods=['POST'])
def check_token_count():

    try:
        print("\n================ NEW REQUEST ================\n", flush=True)

        # STEP 1: Get JSON
        print("[STEP 1] Parsing request JSON...", flush=True)
        data = request.get_json()
        print(f"[DEBUG] Raw request data: {data}", flush=True)

        if not data:
            print("[ERROR] No JSON received", flush=True)
            return jsonify({"error": "No JSON received"}), 400

        if not isinstance(data, dict):
            print("[ERROR] Payload is not dict", flush=True)
            return jsonify({"error": "Invalid JSON format"}), 400

        if "text" not in data:
            print("[ERROR] Missing 'text' key", flush=True)
            return jsonify({"error": "Missing 'text' key"}), 400

        text = data["text"]
        print(f"[STEP 2] Extracted text: {text}", flush=True)
        print(f"[STEP 2] Type of text: {type(text)}", flush=True)

        # STEP 2: Validate input
        if not isinstance(text, str):
            print("[ERROR] TEXT IS NOT STRING → BLOCKING", flush=True)
            return jsonify({
                "error": "text must be a string",
                "received_type": str(type(text)),
                "received_value": str(text)
            }), 400

        # STEP 3: System diagnostics
        print("\n[STEP 3] System diagnostics...", flush=True)
        cache_dir = os.environ.get("TIKTOKEN_CACHE_DIR", "DEFAULT (OS TEMP)")
        print(f"[DEBUG] Cache dir: {cache_dir}", flush=True)

        try:
            print(f"[DEBUG] UID: {os.getuid()}, GID: {os.getgid()}", flush=True)
        except:
            print("[DEBUG] Windows environment detected", flush=True)

        socket.setdefaulttimeout(5.0)
        print("[DEBUG] Socket timeout set to 5 seconds", flush=True)

        # STEP 4: Token counting
        print("\n[STEP 4] Calling count_tokens()", flush=True)
        start_time = time.time()
        token_count = count_tokens(text, DEFAULT_MODEL)
        end_time = time.time()
        print(f"[STEP 4] Token count SUCCESS: {token_count}", flush=True)
        print(f"[DEBUG] Tokenization time: {end_time - start_time}s", flush=True)

        # STEP 5: Fetch token limit — direct function call, no HTTP
        print("\n[STEP 5] Fetching token limit via direct function call...", flush=True)

        try:
            token_limit_response, _ = get_token_limit()  # ← unpack tuple
            token_limit_data = token_limit_response.get_json()
            print(f"[DEBUG] Token limit data: {token_limit_data}", flush=True)

            token_limit = token_limit_data.get("token_limit")

            if token_limit is None:
                print("[ERROR] token_limit missing in response", flush=True)
                return jsonify({"error": "token_limit missing"}), 500

            if not isinstance(token_limit, int):
                print("[ERROR] token_limit not int", flush=True)
                return jsonify({"error": "token_limit is not integer"}), 500

        except Exception as e:
            print("[ERROR] FETCH TOKEN LIMIT FAILED", flush=True)
            print(traceback.format_exc(), flush=True)
            return jsonify({"error": str(e)}), 500

        # STEP 6: Final compare
        print("\n[STEP 6] Comparing values...", flush=True)
        print(f"[DEBUG] token_count = {token_count}", flush=True)
        print(f"[DEBUG] token_limit = {token_limit}", flush=True)

        result = "Success" if token_count < token_limit else "Failure"
        print(f"[RESULT] {result}", flush=True)

        return jsonify({
            "result": result,
            "token_count": token_count,
            "token_limit": token_limit
        }), 200

    except Exception as e:
        print("\n[CRITICAL ERROR - UNHANDLED EXCEPTION]", flush=True)
        print(traceback.format_exc(), flush=True)
        return jsonify({
            "error": str(e),
            "trace": traceback.format_exc()
        }), 500


# =========================
# RUN APP
# =========================
if __name__ == '__main__':
    print("Starting Flask Debug Server...", flush=True)
    app.run(debug=True)
