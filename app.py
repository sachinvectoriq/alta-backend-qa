import requests
import time
import os
import deepl
import psycopg2
from flask import Flask, request, jsonify, send_file, redirect, session
import json
from azure.storage.blob import BlobServiceClient
from onelogin.saml2.auth import OneLogin_Saml2_Auth
import urllib.parse
import datetime
import logging
from saml import saml_login, saml_callback, extract_token
from test_settings_azure import (
    test_translation,
    translate_document,
    validate_connection_string_route,
    run_all_operations
)
from text_translate_deepl import handle_translation_request
from delete_containers import delete_old_containers
from datetime import datetime, timedelta
from azure.storage.blob import BlobServiceClient, generate_blob_sas, BlobSasPermissions
import time
from storing_user_feedback import store_feedback
from deepl_key_test import check_api_key
from saml import extract_token
#from logging_config import log,flush


app = Flask(__name__)

@app.before_request
def before_request_logging():
    # Skip logging for the root path '/'
    if request.path == '/':
        return # Skip further execution for this request

    user_name = request.args.get('user_name', None)
    
    #log("INFO", f"Incoming request: {request.method} {request.path}", user_name=user_name, data={"ip_address": request.remote_addr, "headers": dict(request.headers), "query_params": request.args})
    #flush()


@app.after_request
def after_request_logging(response):
    # Skip logging for the root path '/'
    if request.path == '/':
        return response # Must return the response object even if skipping logging

    user_name = request.args.get('user_name', None)
    #log("INFO", f"Outgoing response for {request.method} {request.path} with status {response.status_code}", user_name=user_name, data={"status_code": response.status_code, "response_size": response.content_length})
    #flush()
    return response


@app.errorhandler(Exception)
def handle_exception(e):
    # Retrieve user_name directly from query parameters, defaulting to None for consistency
    user_name = request.args.get('user_name', None)
    #log("ERROR", f"An unhandled exception occurred: {e}", user_name=user_name, data={"error_type": type(e).__name__, "error_details": str(e), "path": request.path})
    #flush()
    return jsonify({"message": "An internal server error occurred."}), 500


@app.route('/feedback', methods=['POST'])
def add_feedback():
    user_name = request.args.get('user_name', None) # Defaulting to None
    try:
        #log("INFO", "Received request to add feedback.", user_name=user_name)
        feedback_data = request.json
        result = store_feedback(feedback_data)
        #log("INFO", "Feedback storage function returned.", user_name=user_name)
        #flush()
        return result
    except Exception as e:
        #log("ERROR", f"Error in add_feedback route: {e}", user_name=user_name, data={"error_details": str(e)})
        #flush()
        return jsonify({"message": f"Error processing feedback: {e}"}), 500

app.config["SAML_PATH"] = os.path.join(os.path.dirname(os.path.abspath(__file__)), "saml")
app.config["SECRET_KEY"] = os.getenv('JWT_SECRET_KEY')

@app.route('/')
def say_hi():
    user_name = request.args.get('user_name', None) # Defaulting to None
    system = os.getenv('APP_SYSTEM')
    message = 'Hi!'
    return message

# SAML routes
@app.route('/saml/login')
def login():
    user_name = request.args.get('user_name', None) # Defaulting to None
    try:
        #log("INFO", "Initiating SAML login.", user_name=user_name)
        result = saml_login(app.config["SAML_PATH"])
        #log("INFO", "SAML login initiated.", user_name=user_name)
        #flush()
        return result
    except Exception as e:
        #log("ERROR", f"Error in SAML login route: {e}", user_name=user_name, data={"error_details": str(e)})
        #flush()
        return jsonify({"message": f"Error during SAML login: {e}"}), 500


@app.route('/saml/callback', methods=['POST'])
def login_callback():
    user_name = request.args.get('user_name', None) # Defaulting to None
    try:
        #log("INFO", "Received SAML callback.", user_name=user_name)
        result = saml_callback(app.config["SAML_PATH"])
        #log("INFO", "SAML callback processed.", user_name=user_name)
        #flush()
        return result
    except Exception as e:
        #log("ERROR", f"Error in SAML callback route: {e}", user_name=user_name, data={"error_details": str(e)})
        #flush()
        return jsonify({"message": f"Error during SAML callback: {e}"}), 500


@app.route('/saml/token/extract', methods=['POST'])
def func_get_data_from_token():
    user_name = request.args.get('user_name', None) # Defaulting to None
    try:
        #log("INFO", "Request to extract token data.", user_name=user_name)
        result = extract_token()
        #log("INFO", "Token data extracted.", user_name=user_name)
        #flush()
        return result
    except Exception as e:
        #log("ERROR", f"Error in token extraction route: {e}", user_name=user_name, data={"error_details": str(e)})
        #flush()
        return jsonify({"message": f"Error extracting token: {e}"}), 500


@app.route('/translate/deepl/text', methods=['POST'])
def translate():
    user_name = request.args.get('user_name', None) # Defaulting to None
    try:
        #log("INFO", "Received request for DeepL text translation.", user_name=user_name)
        data = request.get_json()
        result = handle_translation_request(data)
        #log("INFO", "DeepL text translation handled.", user_name=user_name)
        #flush()
        return result
    except Exception as e:
        #log("ERROR", f"Error in DeepL text translation route: {e}", user_name=user_name, data={"error_details": str(e)})
        #flush()
        return jsonify({"message": f"Error during DeepL text translation: {e}"}), 500


from text_trans_deepl_secure import handle_translation_request_secure
@app.route('/api/translate/deepl/text', methods=['POST'])
def translate_deepl_secure():
    user_name = request.args.get('user_name', None) # Defaulting to None
    try:
        #log("INFO", "Received secure request for DeepL text translation.", user_name=user_name)
        data = request.get_json()
        result = handle_translation_request_secure(data,user_name)
        #log("INFO", "Secure DeepL text translation handled.", user_name=user_name)
        #flush()
        return result
    except Exception as e:
        #log("ERROR", f"Error in secure DeepL text translation route: {e}", user_name=user_name, data={"error_details": str(e)})
        #flush()
        return jsonify({"message": f"Error during secure DeepL text translation: {e}"}), 500


from deepl_save import save_settings_deepl
@app.route('/settings/deepl/set', methods=['POST'])
def save_deepl_settings():
    user_name = request.args.get('user_name', None) # Defaulting to None
    try:
        #log("INFO", "Received request to save DeepL settings.", user_name=user_name)
        result = save_settings_deepl()
        #log("INFO", "DeepL settings saved.", user_name=user_name)
        #flush()
        return result
    except Exception as e:
        #log("ERROR", f"Error in saving DeepL settings route: {e}", user_name=user_name, data={"error_details": str(e)})
        #flush()
        return jsonify({"message": f"Error saving DeepL settings: {e}"}), 500


from deepl_save_secure import save_settings_deepl_secure
@app.route('/api/settings/deepl/set', methods=['POST'])
def save_deepl_settings_secure():
    user_name = request.args.get('user_name', None) # Defaulting to None
    try:
        #log("INFO", "Received secure request to save DeepL settings.", user_name=user_name)
        result = save_settings_deepl_secure()
        #log("INFO", "Secure DeepL settings saved.", user_name=user_name)
        #flush()
        return result
    except Exception as e:
        #log("ERROR", f"Error in secure DeepL settings saving route: {e}", user_name=user_name, data={"error_details": str(e)})
        #flush()
        return jsonify({"message": f"Error saving secure DeepL settings: {e}"}), 500


from deepl_get import get_settings_deepl
@app.route('/deepl_get/settings/deepl/get', methods=['POST'])
def get_settings_deepl_route():
    user_name = request.args.get('user_name', None) # Defaulting to None
    try:
        #log("INFO", "Received request to get DeepL settings.", user_name=user_name)
        result = get_settings_deepl()
        #log("INFO", "DeepL settings retrieved.", user_name=user_name)
        #flush()
        return result
    except Exception as e:
        #log("ERROR", f"Error in getting DeepL settings route: {e}", user_name=user_name, data={"error_details": str(e)})
        #flush()
        return jsonify({"message": f"Error retrieving DeepL settings: {e}"}), 500


from deepl_get_secure import get_settings_deepl_secure
@app.route('/api/settings/deepl/get', methods=['POST'])
def get_settings_deepl_route_secure():
    user_name = request.args.get('user_name', None) # Defaulting to None
    try:
        #log("INFO", "Received secure request to get DeepL settings.", user_name=user_name)
        result = get_settings_deepl_secure()
        #log("INFO", "Secure DeepL settings retrieved.", user_name=user_name)
        #flush()
        return result
    except Exception as e:
        #log("ERROR", f"Error in secure DeepL settings retrieval route: {e}", user_name=user_name, data={"error_details": str(e)})
        #flush()
        return jsonify({"message": f"Error retrieving secure DeepL settings: {e}"}), 500


@app.route('/settings/azure/test/string', methods=['POST'])
def validate_connection_string_route_handler():
    user_name = request.args.get('user_name', None) # Defaulting to None
    try:
        #log("INFO", "Received request to validate Azure connection string.", user_name=user_name)
        result = validate_connection_string_route()
        #log("INFO", "Azure connection string validation handled.", user_name=user_name)
        #flush()
        return result
    except Exception as e:
        #log("ERROR", f"Error in Azure connection string validation route: {e}", user_name=user_name, data={"error_details": str(e)})
        #flush()
        return jsonify({"message": f"Error validating Azure connection string: {e}"}), 500

@app.route('/settings/azure/test/text_document', methods=['POST'])
def run_all_operations_route():
    user_name = request.args.get('user_name', None) # Defaulting to None
    try:
        #log("INFO", "Received request to run all Azure operations test.", user_name=user_name)
        result = run_all_operations()
        #log("INFO", "Azure operations test handled.", user_name=user_name)
        #flush()
        return result
    except Exception as e:
        #log("ERROR", f"Error in Azure operations test route: {e}", user_name=user_name, data={"error_details": str(e)})
        #flush()
        return jsonify({"message": f"Error during Azure operations test: {e}"}), 500


from text_trans_azure import text_trans_azure
@app.route('/translate/azure/text', methods=['POST'])
def call_text_trans_azure():
    user_name = request.args.get('user_name', None) # Defaulting to None
    try:
        #log("INFO", "Received request for Azure text translation.", user_name=user_name)
        result = text_trans_azure()
        #log("INFO", "Azure text translation handled.", user_name=user_name)
        #flush()
        return result
    except Exception as e:
        #log("ERROR", f"Error in Azure text translation route: {e}", user_name=user_name, data={"error_details": str(e)})
        #flush()
        return jsonify({"message": f"Error during Azure text translation: {e}"}), 500


from text_trans_azure_secure import text_trans_azure_secure
@app.route('/api/translate/azure/text', methods=['POST'])
def call_text_trans_azure_secure():
    user_name = request.args.get('user_name', None) # Defaulting to None
    try:
        #log("INFO", "Received secure request for Azure text translation.", user_name=user_name)
        result = text_trans_azure_secure(user_name)
        #log("INFO", "Secure Azure text translation handled.", user_name=user_name)
        #flush()
        return result
    except Exception as e:
        #log("ERROR", f"Error in secure Azure text translation route: {e}", user_name=user_name, data={"error_details": str(e)})
        #flush()
        return jsonify({"message": f"Error during secure Azure text translation: {e}"}), 500


from retrieve_settings import retrieve_settings
@app.route('/settings/azure/get', methods=['GET'])
def retrieve_settings_route():
    user_name = request.args.get('user_name', None) # Defaulting to None
    try:
        #log("INFO", "Received request to retrieve Azure settings.", user_name=user_name)
        result = retrieve_settings()
        #log("INFO", "Azure settings retrieved.", user_name=user_name)
        #flush()
        return result
    except Exception as e:
        #log("ERROR", f"Error in retrieving Azure settings route: {e}", user_name=user_name, data={"error_details": str(e)})
        #flush()
        return jsonify({"message": f"Error retrieving Azure settings: {e}"}), 500

from retrieve_settings_secure import retrieve_settings_secure
@app.route('/api/settings/azure/get', methods=['GET'])
def retrieve_settings_route_secure():
    user_name = request.args.get('user_name', None) # Defaulting to None
    try:
        #log("INFO", "Received secure request to retrieve Azure settings.", user_name=user_name)
        result = retrieve_settings_secure()
        #log("INFO", "Secure Azure settings retrieved.", user_name=user_name)
        #flush()
        return result
    except Exception as e:
        #log("ERROR", f"Error in secure Azure settings retrieval route: {e}", user_name=user_name, data={"error_details": str(e)})
        #flush()
        return jsonify({"message": f"Error retrieving secure Azure settings: {e}"}), 500


from save_settings import save_settings
@app.route('/settings/azure/set',methods=['POST'])
def call_save_settings():
    user_name = request.args.get('user_name', None) # Defaulting to None
    try:
        #log("INFO", "Received request to save Azure settings.", user_name=user_name)
        result = save_settings()
        #log("INFO", "Azure settings saved.", user_name=user_name)
        #flush()
        return result
    except Exception as e:
        #log("ERROR", f"Error in saving Azure settings route: {e}", user_name=user_name, data={"error_details": str(e)})
        #flush()
        return jsonify({"message": f"Error saving Azure settings: {e}"}), 500


from save_settings_secure import save_settings_secure
@app.route('/api/settings/azure/set',methods=['POST'])
def call_save_settings_secure():
    user_name = request.args.get('user_name', None) # Defaulting to None
    try:
        #log("INFO", "Received secure request to save Azure settings.", user_name=user_name)
        result = save_settings_secure()
        #log("INFO", "Secure Azure settings saved.", user_name=user_name)
        #flush()
        return result
    except Exception as e:
        #log("ERROR", f"Error in secure Azure settings saving route: {e}", user_name=user_name, data={"error_details": str(e)})
        #flush()
        return jsonify({"message": f"Error saving secure Azure settings: {e}"}), 500


# from multiple_files2 import multiple_files2
# @app.route('/translate/deepl/documents',methods=['POST'])
# def call_multiple_files2():
#       return multiple_files2()

@app.route('/delete/containers', methods=['DELETE'])
def delete_old_containers_route():
    user_name = request.args.get('user_name', None) # Defaulting to None
    try:
        #log("INFO", "Received request to delete old containers.", user_name=user_name)
        result = delete_old_containers()
        #log("INFO", "Old containers deletion handled.", user_name=user_name)
        #flush()
        return result
    except Exception as e:
        #log("ERROR", f"Error in deleting old containers route: {e}", user_name=user_name, data={"error_details": str(e)})
        #flush()
        return jsonify({"message": f"Error deleting old containers: {e}"}), 500

# Route to check API key validity
@app.route('/settings/deepl/test', methods=['POST'])
def handle_check_api_key():
    user_name = request.args.get('user_name', None) # Defaulting to None
    try:
        #log("INFO", "Received request to check DeepL API key validity.", user_name=user_name)
        result = check_api_key()
        #log("INFO", "DeepL API key validity check handled.", user_name=user_name)
        #flush()
        return result
    except Exception as e:
        #log("ERROR", f"Error in DeepL API key check route: {e}", user_name=user_name, data={"error_details": str(e)})
        #flush()
        return jsonify({"message": f"Error checking DeepL API key: {e}"}), 500


# from docu_trans_azure2 import docu_trans_azure2
# @app.route('/translate/azure/documents',methods=['POST'])
# def docu_trans2():
#       return docu_trans_azure2()


from create_glossary_deepl2 import upload_glossary
@app.route('/upload_glossary',methods=['POST'])
def call_upload_glossary():
    user_name = request.args.get('user_name', None) # Defaulting to None
    try:
        #log("INFO", "Received request to upload DeepL glossary.", user_name=user_name)
        result = upload_glossary()
        #log("INFO", "DeepL glossary upload handled.", user_name=user_name)
        #flush()
        return result
    except Exception as e:
        #log("ERROR", f"Error in DeepL glossary upload route: {e}", user_name=user_name, data={"error_details": str(e)})
        #flush()
        return jsonify({"message": f"Error uploading DeepL glossary: {e}"}), 500


from docu_azure_get_job_id import docu_trans_azure2
@app.route('/translate/azure/documents', methods=['POST'])
def docutransazure2():
    user_name = request.args.get('user_name', None) # Defaulting to None
    try:
        #log("INFO", "Received request for Azure document translation.", user_name=user_name)
        result = docu_trans_azure2()
        #log("INFO", "Azure document translation handled.", user_name=user_name)
        #flush()
        return result
    except Exception as e:
        #log("ERROR", f"Error in Azure document translation route: {e}", user_name=user_name, data={"error_details": str(e)})
        #flush()
        return jsonify({"message": f"Error during Azure document translation: {e}"}), 500


from docu_azure_get_job_id_secure import docu_trans_azure2_secure
@app.route('/api/translate/azure/documents', methods=['POST'])
def call_docutransazure2_secure():
    user_name = request.args.get('user_name', None) # Defaulting to None
    try:
        #log("INFO", "Received secure request for Azure document translation.", user_name=user_name)
        result = docu_trans_azure2_secure()
        #log("INFO", "Secure Azure document translation handled.", user_name=user_name)
        #flush()
        return result
    except Exception as e:
        #log("ERROR", f"Error in secure Azure document translation route: {e}", user_name=user_name, data={"error_details": str(e)})
        #flush()
        return jsonify({"message": f"Error during secure Azure document translation: {e}"}), 500


from docu_azure_get_sasurl import translation_status
@app.route('/translate/azure/documents/status', methods=['POST'])
def azuretranslationstatus():
    user_name = request.args.get('user_name', None) # Defaulting to None
    try:
        #log("INFO", "Received request for Azure document translation status.", user_name=user_name)
        result = translation_status()
        #log("INFO", "Azure document translation status retrieved.", user_name=user_name)
        #flush()
        return result
    except Exception as e:
        #log("ERROR", f"Error in Azure document translation status route: {e}", user_name=user_name, data={"error_details": str(e)})
        #flush()
        return jsonify({"message": f"Error checking Azure translation status: {e}"}), 500


from docu_azure_get_sasurl_secure import translation_status
@app.route('/api/translate/azure/documents/status', methods=['POST'])
def azuretranslationstatus_secure():
    user_name = request.args.get('user_name', None) # Defaulting to None
    try:
        #log("INFO", "Received secure request for Azure document translation status.", user_name=user_name)
        result = translation_status()
        #log("INFO", "Secure Azure document translation status retrieved.", user_name=user_name)
        #flush()
        return result
    except Exception as e:
        #log("ERROR", f"Error in secure Azure document translation status route: {e}", user_name=user_name, data={"error_details": str(e)})
        #flush()
        return jsonify({"message": f"Error checking secure Azure translation status: {e}"}), 500


from docu_deepl_get_document_info import multiple_files3
@app.route('/translate/deepl/documents',methods=['POST'])
def call_multiple_files3():
    user_name = request.args.get('user_name', None) # Defaulting to None
    try:
        #log("INFO", "Received request for DeepL document translation.", user_name=user_name)
        result = multiple_files3()
        #log("INFO", "DeepL document translation handled.", user_name=user_name)
        #flush()
        return result
    except Exception as e:
        #log("ERROR", f"Error in DeepL document translation route: {e}", user_name=user_name, data={"error_details": str(e)})
        #flush()
        return jsonify({"message": f"Error during DeepL document translation: {e}"}), 500

from docu_deepl_get_document_info_secure import multiple_files3_secure
@app.route('/api/translate/deepl/documents',methods=['POST'])
def call_multiple_files3_securely():
    user_name = request.args.get('user_name', None) # Defaulting to None
    try:
        #log("INFO", "Received secure request for DeepL document translation.", user_name=user_name)
        result = multiple_files3_secure()
        #log("INFO", "Secure DeepL document translation handled.", user_name=user_name)
        #flush()
        return result
    except Exception as e:
        #log("ERROR", f"Error in secure DeepL document translation route: {e}", user_name=user_name, data={"error_details": str(e)})
        #flush()
        return jsonify({"message": f"Error during secure DeepL document translation: {e}"}), 500


from docu_deepl_get_sasurl import download_translate_upload
@app.route('/translate/deepl/documents/status',methods=['POST'])
def call_process_translated_document():
    user_name = request.args.get('user_name', None) # Defaulting to None
    try:
        #log("INFO", "Received request to process DeepL translated document (download/upload).", user_name=user_name)
        result = download_translate_upload()
        #log("INFO", "DeepL translated document processing handled.", user_name=user_name)
        #flush()
        return result
    except Exception as e:
        #log("ERROR", f"Error in DeepL document processing route: {e}", user_name=user_name, data={"error_details": str(e)})
        #flush()
        return jsonify({"message": f"Error processing DeepL translated document: {e}"}), 500

from docu_deepl_get_sasurl_secure import download_translate_upload_secure
@app.route('/api/translate/deepl/documents/status',methods=['POST'])
def call_process_translated_document_secure():
    user_name = request.args.get('user_name', None) # Defaulting to None
    try:
        #log("INFO", "Received secure request to process DeepL translated document (download/upload).", user_name=user_name)
        result = download_translate_upload_secure()
        #log("INFO", "Secure DeepL translated document processing handled.", user_name=user_name)
        #flush()
        return result
    except Exception as e:
        #log("ERROR", f"Error in secure DeepL document processing route: {e}", user_name=user_name, data={"error_details": str(e)})
        #flush()
        return jsonify({"message": f"Error processing secure DeepL translated document: {e}"}), 500


from docu_deepl_get_document_status import check_status
@app.route('/translate/deepl/documents/check/status',methods=['POST'])
def call_check_status():
    user_name = request.args.get('user_name', None) # Defaulting to None
    try:
        #log("INFO", "Received request to check DeepL document translation status.", user_name=user_name)
        result = check_status()
        #log("INFO", "DeepL document translation status check handled.", user_name=user_name)
        #flush()
        return result
    except Exception as e:
        #log("ERROR", f"Error in DeepL document translation status check route: {e}", user_name=user_name, data={"error_details": str(e)})
        #flush()
        return jsonify({"message": f"Error checking DeepL translation status: {e}"}), 500

from docu_deepl_get_document_status_secure import check_status_secure
@app.route('/api/translate/deepl/documents/check/status',methods=['POST'])
def call_check_status_secure():
    user_name = request.args.get('user_name', None) # Defaulting to None
    try:
        #log("INFO", "Received secure request to check DeepL document translation status.", user_name=user_name)
        result = check_status_secure()
        #log("INFO", "Secure DeepL document translation status check handled.", user_name=user_name)
        #flush()
        return result
    except Exception as e:
        #log("ERROR", f"Error in secure DeepL document translation status check route: {e}", user_name=user_name, data={"error_details": str(e)})
        #flush()
        return jsonify({"message": f"Error checking secure DeepL translation status: {e}"}), 500


from delete_files_from_deepl_container import delete_old_files_in_container
@app.route('/delete/files/deepl',methods=['DELETE'])
def call_delete_deepl_files_function():
    user_name = request.args.get('user_name', None) # Defaulting to None
    try:
        #log("INFO", "Received request to delete old DeepL files from container.", user_name=user_name)
        result = delete_old_files_in_container()
        #log("INFO", "DeepL files deletion handled.", user_name=user_name)
        #flush()
        return result
    except Exception as e:
        #log("ERROR", f"Error in deleting DeepL files route: {e}", user_name=user_name, data={"error_details": str(e)})
        #flush()
        return jsonify({"message": f"Error deleting DeepL files: {e}"}), 500


from user_login_log import log_user_login
@app.route('/log/user/login',methods=['POST'])
def call_log_user_login():
    user_name = request.args.get('user_name', None) # Defaulting to None
    try:
        #log("INFO", "Received request to log user login.", user_name=user_name)
        result = log_user_login()
        #log("INFO", "User login logged.", user_name=user_name)
        #flush()
        return result
    except Exception as e:
        #log("ERROR", f"Error in user login log route: {e}", user_name=user_name, data={"error_details": str(e)})
        #flush()
        return jsonify({"message": f"Error logging user login: {e}"}), 500


from user_text_trans_log import log_text_translation
@app.route('/log/text/translation',methods=['POST'])
def call_log_text_translation():
    user_name = request.args.get('user_name', None) # Defaulting to None
    try:
        #log("INFO", "Received request to log text translation.", user_name=user_name)
        result = log_text_translation()
        #log("INFO", "Text translation logged.", user_name=user_name)
        #flush()
        return result
    except Exception as e:
        #log("ERROR", f"Error in text translation log route: {e}", user_name=user_name, data={"error_details": str(e)})
        #flush()
        return jsonify({"message": f"Error logging text translation: {e}"}), 500

from user_docu_trans_log import log_document_translation
@app.route('/log/document/translation',methods=['POST'])
def call_log_docu_translation():
    user_name = request.args.get('user_name', None) # Defaulting to None
    try:
        #log("INFO", "Received request to log document translation.", user_name=user_name)
        result = log_document_translation()
        #log("INFO", "Document translation logged.", user_name=user_name)
        #flush()
        return result
    except Exception as e:
        #log("ERROR", f"Error in document translation log route: {e}", user_name=user_name, data={"error_details": str(e)})
        #flush()
        return jsonify({"message": f"Error logging document translation: {e}"}), 500


# from context_in_translation import refine_text
# @app.route('/refine_text',methods=['POST'])
# def call_refine_text():
#       return refine_text()


# from to_check_whitespaces import upload_file
# @app.route('/check_glossary_file',methods=['POST'])
# def call_upload_file():
#       return upload_file()


from alta_filters_add import add_alta_filter
@app.route('/alta_filters/add',methods=['POST'])
def call_add_alta_filter():
    user_name = request.args.get('user_name', None) # Defaulting to None
    try:
        #log("INFO", "Received request to add Alta filter.", user_name=user_name)
        result = add_alta_filter()
        #log("INFO", "Alta filter added.", user_name=user_name)
        #flush()
        return result
    except Exception as e:
        #log("ERROR", f"Error in adding Alta filter route: {e}", user_name=user_name, data={"error_details": str(e)})
        #flush()
        return jsonify({"message": f"Error adding Alta filter: {e}"}), 500


from alta_filter_update_columns_using_id import update_filter
@app.route('/alta_filters/update_filter', methods=['PUT'])
def call_update_filter():
    user_name = request.args.get('user_name', None) # Defaulting to None
    try:
        #log("INFO", "Received request to update Alta filter.", user_name=user_name)
        result = update_filter()
        #log("INFO", "Alta filter updated.", user_name=user_name)
        #flush()
        return result
    except Exception as e:
        #log("ERROR", f"Error in updating Alta filter route: {e}", user_name=user_name, data={"error_details": str(e)})
        #flush()
        return jsonify({"message": f"Error updating Alta filter: {e}"}), 500


from alta_filters_table_dump import get_grouped_filters
@app.route('/alta_filters/grouped_modifiers', methods=['POST'])
def call_get_grouped_filters():
    user_name = request.args.get('user_name', None) # Defaulting to None
    try:
        #log("INFO", "Received request to get grouped Alta filters.", user_name=user_name)
        result = get_grouped_filters()
        #log("INFO", "Grouped Alta filters retrieved.", user_name=user_name)
        #flush()
        return result
    except Exception as e:
        #log("ERROR", f"Error in getting grouped Alta filters route: {e}", user_name=user_name, data={"error_details": str(e)})
        #flush()
        return jsonify({"message": f"Error getting grouped Alta filters: {e}"}), 500


from alta_filters_distinct_modifier import get_distinct_modifiers
@app.route('/alta_filters/distinct/modifier', methods=['POST'])
def call_get_distinct_modifiers():
    user_name = request.args.get('user_name', None) # Defaulting to None
    try:
        #log("INFO", "Received request to get distinct Alta modifiers.", user_name=user_name)
        result = get_distinct_modifiers()
        #log("INFO", "Distinct Alta modifiers retrieved.", user_name=user_name)
        #flush()
        return result
    except Exception as e:
        #log("ERROR", f"Error in getting distinct Alta modifiers route: {e}", user_name=user_name, data={"error_details": str(e)})
        #flush()
        return jsonify({"message": f"Error getting distinct Alta modifiers: {e}"}), 500

from alta_filters_delete_id import handle_delete_request
@app.route('/alta_filters/delete', methods=['DELETE'])
def call_delete_row():
    user_name = request.args.get('user_name', None) # Defaulting to None
    try:
        #log("INFO", "Received request to delete Alta filter by ID.", user_name=user_name)
        result = handle_delete_request()
        #log("INFO", "Alta filter deleted by ID.", user_name=user_name)
        #flush()
        return result
    except Exception as e:
        #log("ERROR", f"Error in deleting Alta filter by ID route: {e}", user_name=user_name, data={"error_details": str(e)})
        #flush()
        return jsonify({"message": f"Error deleting Alta filter by ID: {e}"}), 500


from alta_filters_delete_modifier import delete_modifier
@app.route('/alta_filters/delete_modifier', methods=['DELETE'])
def call_delete_mofifier():
    user_name = request.args.get('user_name', None) # Defaulting to None
    try:
        #log("INFO", "Received request to delete Alta modifier.", user_name=user_name)
        result = delete_modifier()
        #log("INFO", "Alta modifier deleted.", user_name=user_name)
        #flush()
        return result
    except Exception as e:
        #log("ERROR", f"Error in deleting Alta modifier route: {e}", user_name=user_name, data={"error_details": str(e)})
        #flush()
        return jsonify({"message": f"Error deleting Alta modifier: {e}"}), 500


from alta_filters_filter_id import get_filter
@app.route('/alta_filters/id', methods=['POST'])
def call_get_filter():
    user_name = request.args.get('user_name', None) # Defaulting to None
    try:
        #log("INFO", "Received request to get Alta filter by ID.", user_name=user_name)
        result = get_filter()
        #log("INFO", "Alta filter retrieved by ID.", user_name=user_name)
        #flush()
        return result
    except Exception as e:
        #log("ERROR", f"Error in getting Alta filter by ID route: {e}", user_name=user_name, data={"error_details": str(e)})
        #flush()
        return jsonify({"message": f"Error getting Alta filter by ID: {e}"}), 500

from contextsense_core_prompt_add import add_prompt
@app.route('/core_prompt/add', methods=['POST'])
def call_add_prompt():
    user_name = request.args.get('user_name', None) # Defaulting to None
    try:
        #log("INFO", "Received request to add core prompt.", user_name=user_name)
        result = add_prompt()
        #log("INFO", "Core prompt added.", user_name=user_name)
        #flush()
        return result
    except Exception as e:
        #log("ERROR", f"Error in adding core prompt route: {e}", user_name=user_name, data={"error_details": str(e)})
        #flush()
        return jsonify({"message": f"Error adding core prompt: {e}"}), 500


from contextsense_core_prompt_fetch_id import get_prompt
@app.route('/core_prompt/get', methods=['GET'])
def call_get_prompt():
    user_name = request.args.get('user_name', None) # Defaulting to None
    try:
        #log("INFO", "Received request to get core prompt.", user_name=user_name)
        result = get_prompt()
        #log("INFO", "Core prompt retrieved.", user_name=user_name)
        #flush()
        return result
    except Exception as e:
        #log("ERROR", f"Error in getting core prompt route: {e}", user_name=user_name, data={"error_details": str(e)})
        #flush()
        return jsonify({"message": f"Error getting core prompt: {e}"}), 500


from contextsense_core_prompt_delete import delete_core_prompt
@app.route('/core_prompt/delete_core_prompt', methods=['DELETE'])
def call_delete_core_prompt():
    user_name = request.args.get('user_name', None) # Defaulting to None
    try:
        #log("INFO", "Received request to delete core prompt.", user_name=user_name)
        result = delete_core_prompt()
        #log("INFO", "Core prompt deleted.", user_name=user_name)
        #flush()
        return result
    except Exception as e:
        #log("ERROR", f"Error in deleting core prompt route: {e}", user_name=user_name, data={"error_details": str(e)})
        #flush()
        return jsonify({"message": f"Error deleting core prompt: {e}"}), 500

from process_context_sense import process_context_sense
@app.route('/process_context_sense', methods=['POST'])
def call_process_context_sense():
    user_name = request.args.get('user_name', None) # Defaulting to None
    try:
        #log("INFO", "Received request to process context sense.", user_name=user_name)
        result = process_context_sense()
        #log("INFO", "Context sense processed.", user_name=user_name)
        #flush()
        return result
    except Exception as e:
        #log("ERROR", f"Error in processing context sense route: {e}", user_name=user_name, data={"error_details": str(e)})
        #flush()
        return jsonify({"message": f"Error processing context sense: {e}"}), 500


from contextsense_core_prompt_id_updated import update_prompt
@app.route('/core_prompt/update', methods=['PUT'])
def call_update_prompt():
    user_name = request.args.get('user_name', None) # Defaulting to None
    try:
        #log("INFO", "Received request to update core prompt.", user_name=user_name)
        result = update_prompt()
        #log("INFO", "Core prompt updated.", user_name=user_name)
        #flush()
        return result
    except Exception as e:
        #log("ERROR", f"Error in updating core prompt route: {e}", user_name=user_name, data={"error_details": str(e)})
        #flush()
        return jsonify({"message": f"Error updating core prompt: {e}"}), 500

from log_text_contextsense import log_contextsense
@app.route('/log_contextsense', methods=['POST'])
def log_context_sense():
    user_name = request.args.get('user_name', None) # Defaulting to None
    try:
        #log("INFO", "Received request to log contextsense.", user_name=user_name)
        result = log_contextsense()
        #log("INFO", "Contextsense logged.", user_name=user_name)
        #flush()
        return result
    except Exception as e:
        #log("ERROR", f"Error in logging contextsense route: {e}", user_name=user_name, data={"error_details": str(e)})
        #flush()
        return jsonify({"message": f"Error logging contextsense: {e}"}), 500


from update_sequence import update_modifier_sequence
@app.route('/update_modifier_sequence', methods=['POST'])
def update_sequence():
    user_name = request.args.get('user_name', None) # Defaulting to None
    try:
        #log("INFO", "Received request to update modifier sequence.", user_name=user_name)
        result = update_modifier_sequence()
        #log("INFO", "Modifier sequence updated.", user_name=user_name)
        #flush()
        return result
    except Exception as e:
        #log("ERROR", f"Error in updating modifier sequence route: {e}", user_name=user_name, data={"error_details": str(e)})
        #flush()
        return jsonify({"message": f"Error updating modifier sequence: {e}"}), 500


from update_modifier_status import update_modifier_status
@app.route('/update_modifier_status', methods=['POST'])
def update_status():
    user_name = request.args.get('user_name', None) # Defaulting to None
    try:
        #log("INFO", "Received request to update modifier status.", user_name=user_name)
        result = update_modifier_status()
        #log("INFO", "Modifier status updated.", user_name=user_name)
        #flush()
        return result
    except Exception as e:
        #log("ERROR", f"Error in updating modifier status route: {e}", user_name=user_name, data={"error_details": str(e)})
        #flush()
        return jsonify({"message": f"Error updating modifier status: {e}"}), 500


from fetch_token_limit import get_token_limit
@app.route('/get_token_limit', methods=['GET'])
def fetch_limit():
    user_name = request.args.get('user_name', None) # Defaulting to None
    try:
        #log("INFO", "Received request to fetch token limit.", user_name=user_name)
        result = get_token_limit()
        #log("INFO", "Token limit fetched.", user_name=user_name)
        #flush()
        return result
    except Exception as e:
        #log("ERROR", f"Error in fetching token limit route: {e}", user_name=user_name, data={"error_details": str(e)})
        #flush()
        return jsonify({"message": f"Error fetching token limit: {e}"}), 500


from set_limit import update_token_limit
@app.route('/set_token', methods=['POST'])
def setlimit():
    user_name = request.args.get('user_name', None) # Defaulting to None
    try:
        #log("INFO", "Received request to set token limit.", user_name=user_name)
        result = update_token_limit()
        #log("INFO", "Token limit set.", user_name=user_name)
        #flush()
        return result
    except Exception as e:
        #log("ERROR", f"Error in setting token limit route: {e}", user_name=user_name, data={"error_details": str(e)})
        #flush()
        return jsonify({"message": f"Error setting token limit: {e}"}), 500


from check_token import check_token_count
@app.route('/check_token_count', methods=['POST'])
def check_token():
    user_name = request.args.get('user_name', None) # Defaulting to None
    try:
        #log("INFO", "Received request to check token count.", user_name=user_name)
        result = check_token_count()
        #log("INFO", "Token count checked.", user_name=user_name)
        #flush()
        return result
    except Exception as e:
        #log("ERROR", f"Error in checking token count route: {e}", user_name=user_name, data={"error_details": str(e)})
        #flush()
        return jsonify({"message": f"Error checking token count: {e}"}), 500

from total_rows import get_table_row_count
@app.route('/table_row_count', methods=['GET'])
def total_row_count():
    user_name=request.args.get('user_name',None)
    try:
        #log("INFO", "Received request to table row count.", user_name=user_name)
        result = get_table_row_count()
        #log("INFO", "total row API responded", user_name=user_name)
        #flush()
        return result
    except Exception as e:
        #log("ERROR", f"Error in total row count route: {e}", user_name=user_name, data={"error_details": str(e)})
        #flush()
        return jsonify({"message": f"Error checking total row count: {e}"}), 500


from export_report import export_table_data
@app.route('/export_table_data', methods=['GET'])
def export_report():
    user_name=request.args.get('user_name',None)
    try:
        #log("INFO", "Received request to export report.", user_name=user_name)
        result = export_table_data()
        #log("INFO", "export report API responded", user_name=user_name)
        #flush()
        return result
    except Exception as e:
        #log("ERROR", f"Error in checking export report route: {e}", user_name=user_name, data={"error_details": str(e)})
        #flush()
        return jsonify({"message": f"Error with exporting report: {e}"}), 500



from doc_report import get_doc_data_report
@app.route('/doc_data_report', methods=['GET'])
def doc_data_report():
    user_name=request.args.get('user_name',None)
    try:
        #log("INFO", "Received request to fetch doc audit report", user_name=user_name)
        result = get_doc_data_report()
        #log("INFO", "doc_data_report responded API responded", user_name=user_name)
        #flush()
        return result
    except Exception as e:
        #log("ERROR", f"Error in checking doc_data_report route: {e}", user_name=user_name, data={"error_details": str(e)})
        #flush()
        return jsonify({"message": f"Error checking doc_audit_report: {e}"}), 500
        
from text_report import get_text_data_report
@app.route('/text_data_report', methods=['GET'])
def text_data_report():
    user_name=request.args.get('user_name',None)
    try:
        #log("INFO", "Received request to fetch text audit report", user_name=user_name)
        result = get_text_data_report()
        #log("INFO", "text_data_report responded API responded", user_name=user_name)
        #flush()
        return result
    except Exception as e:
        #log("ERROR", f"Error in checking text_data_report route: {e}", user_name=user_name, data={"error_details": str(e)})
        #flush()
        return jsonify({"message": f"Error checking text_audit_report: {e}"}), 500


from contextsense_report import get_contextsense_data_report
@app.route('/contextsense_data_report', methods=['GET'])
def contextsense_report():
    user_name=request.args.get('user_name',None)
    try:
        #log("INFO", "Received request to fetch contextsense audit report", user_name=user_name)
        result = get_contextsense_data_report()
        #log("INFO", "contextsense_data_report responded API responded", user_name=user_name)
        #flush()
        return result
    except Exception as e:
        #log("ERROR", f"Error in checking contextsense_data_report route: {e}", user_name=user_name, data={"error_details": str(e)})
        #flush()
        return jsonify({"message": f"Error checking contextsense_audit_report: {e}"}), 500

from user_report import get_user_login_report
@app.route('/user_login_report', methods=['GET'])
def user_report():
    user_name=request.args.get('user_name',None)
    try:
        #log("INFO", "Received request to fetch user report", user_name=user_name)
        result = get_user_login_report()
        #log("INFO", "user_data_report responded API responded", user_name=user_name)
        #flush()
        return result
    except Exception as e:
        #log("ERROR", f"Error in checking user_data_report route: {e}", user_name=user_name, data={"error_details": str(e)})
        #flush()
        return jsonify({"message": f"Error checking user_audit_report: {e}"}), 500


from database_api import fetch_access_endpoint, delete_access_endpoint, insert_access_endpoint

@app.route('/insert_access', methods=['POST'])
def insert_access():
    user_name = request.args.get('user_name', None)
    try:
        #log("INFO", "Received request to insert access to reports", user_name=user_name)
        result = insert_access_endpoint()
        #log("INFO", "insert access endpoint responded API responded", user_name=user_name)
        #flush()
        return result
    except Exception as e:
        #log("ERROR", f"Error in checking insert access to report route: {e}", user_name=user_name,data={"error_details": str(e)})
        #flush()
        return jsonify({"message": f"Error checking insert access: {e}"}), 500

@app.route('/delete_access/<int:record_id>', methods=['DELETE'])
def delete_access(record_id):
    user_name = request.args.get('user_name', None)
    try:
        #log("INFO", "Received request to delete access to reports", user_name=user_name)
        result = delete_access_endpoint(record_id)
        #log("INFO", "delete access endpoint responded API responded", user_name=user_name)
        #flush()
        return result
    except Exception as e:
        #log("ERROR", f"Error in checking delete access to report route: {e}", user_name=user_name,data={"error_details": str(e)})
        #flush()
        return jsonify({"message": f"Error checking delete access: {e}"}), 500

@app.route('/fetch_access', methods=['GET'])
def fetch_access():
    user_name = request.args.get('user_name', None)
    try:
        #log("INFO", "Received request to fetch access to reports", user_name=user_name)
        result = fetch_access_endpoint()
        #log("INFO", "fetch access endpoint responded API responded", user_name=user_name)
        #flush()
        return result
    except Exception as e:
        #log("ERROR", f"Error in checking fetch access to report route: {e}", user_name=user_name,data={"error_details": str(e)})
        #flush()
        return jsonify({"message": f"Error checking fetch access: {e}"}), 500


from reports_uniquecolnames import get_unique_values
@app.route('/unique-values', methods=['GET'])
def unique_colvalues():
    user_name = request.args.get('user_name', None)
    try:
        #log("INFO", "Received request to fetch access to reports", user_name=user_name)
        result = get_unique_values()
        #log("INFO", "fetch access endpoint responded API responded", user_name=user_name)
        #flush()
        return result
    except Exception as e:
        #log("ERROR", f"Error in checking fetch access to report route: {e}", user_name=user_name,data={"error_details": str(e)})
        #flush()
        return jsonify({"message": f"Error checking fetch access: {e}"}), 500


from translation_metrics import translation_metrics
@app.route('/translation/metrics', methods=['POST'])
def call_translation_metrics():
    return translation_metrics()



if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    #log("INFO", f"Starting Flask application on port {port}.", user_name=None) # Using None for startup
#flush()
    app.run(host='0.0.0.0', port=port)






