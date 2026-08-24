from flask import Flask, request, jsonify
from pydantic import BaseModel, Field, ValidationError
from typing import Optional, Dict, List
from langchain_openai import AzureChatOpenAI
from langchain.prompts import PromptTemplate
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.output_parsers import PydanticOutputParser
import json
import re
from dotenv import load_dotenv
import os
import datetime
import requests
import psycopg2
import uuid
import sys
from typing import Any
#from logging_config import logger
import pandas as pd
from azure.identity import DefaultAzureCredential, get_bearer_token_provider


app = Flask(__name__)
load_dotenv()

class TextInput(BaseModel):
    user_id: int
    core_system_prompt_id: int
    translated_text: str
    source_text: str
    source_language: str
    target_language: str
    user_context_id: Optional[int] = None
    user_context_value: Optional[str] = None
    user_tone_id: Optional[int] = None
    user_tone_value: Optional[str] = None
    user_domain_id: Optional[int] = None
    user_domain_value: Optional[str] = None
    user_coherence_id: Optional[int] = None
    user_coherence_value: Optional[str] = None
    user_audience_id: Optional[int] = None
    user_audience_value: Optional[str] = None

class RefinedOutput(BaseModel):
    refined_text: str = Field(description="The refined text.")
    explanation: str = Field(description="Explanation of the refinements made.")

DB_CONFIG = {
    'dbname': os.getenv('DB_NAME'),
    'user': os.getenv('DB_USER'),
    'password': os.getenv('DB_PASSWORD'),
    'host': os.getenv('DB_HOST'),
    'port': os.getenv('DB_PORT')
}


# --- Global DataFrame for Context Prompts ---
PROMPT_DATA_FRAME: Optional[pd.DataFrame] = None

def connect_db():
    """Establishes a connection to the PostgreSQL database."""
    try:
        connection = psycopg2.connect(**DB_CONFIG)
        print("Connected to database")
        return connection
    except psycopg2.Error as e:
        print(f"Error connecting to the database: {e}")
        return None





# def get_openai_key_from_keyvault():
#     credential = DefaultAzureCredential()
#     kv_url = "https://kv-aicoe.vault.azure.net/"
#     secret_name = "openaikey"  # replace with your secret

#     client = SecretClient(vault_url=kv_url, credential=credential)
#     secret = client.get_secret(secret_name)

#     return secret.value
# ADD this in its place
def get_azure_openai_token_provider():
    credential = DefaultAzureCredential()
    return get_bearer_token_provider(
        credential, "https://cognitiveservices.azure.com/.default"
    )





def log_message(connection, level: str, message: str, log_data: dict[str, Any] | None = None, session_id: str | None = None) -> None:
    """
    Logs a message to the database.

    Args:
        connection: The PostgreSQL database connection.
        level: The log level (e.g., 'INFO', 'ERROR').
        message: The log message.
        log_data: A dictionary containing additional data to be logged (optional).
    """
    if connection is None:
        print("Database connection is None. Cannot log message.")
        return  # IMPORTANT: Exit if no connection

    cursor = connection.cursor()
    timestamp = datetime.datetime.now()
    try:
        # Use a parameterized query to prevent SQL injection
        if session_id:  # check if session_id exists
            cursor.execute(
                "INSERT INTO logs (timestamp, level, log, data, session_id) VALUES (%s, %s, %s, %s, %s)",
                # Added session_id
                (timestamp, level, message, json.dumps(log_data) if log_data else None, session_id)
            )
        else:
            cursor.execute(
                "INSERT INTO logs (timestamp, level, log, data, session_id) VALUES (%s, %s, %s, %s, %s)",
                # Added session_id
                (timestamp, level, message, json.dumps(log_data) if log_data else None, None)
            )
        connection.commit()
    except psycopg2.Error as e:
        print(f"Error logging to database: {e}")
        connection.rollback()  # Rollback on error, to avoid partial writes.
    finally:
        cursor.close()  # Ensure the cursor is closed.
def dynamic_json_parser(llm_output, user_id):
    #logger.info(f"user id:{user_id}--dynamic_json_parser is being used to convert llm to json format")

    # 1. Remove code blocks (```json ... ```)
    llm_output = re.sub(r"```(?:json)?\s*([\s\S]*?)\s*```", r"\1", llm_output).strip()

    # 2. Remove any leading/trailing whitespace or newlines
    llm_output = llm_output.strip()

    # 3. Handle cases where LLM might return a JSON-like string with extra text
    if llm_output.startswith("{") and llm_output.endswith("}"):
        try:
            #logger.info(f"user id:{user_id}--llm output parsing, Handle cases where LLM might return a JSON-like string with extra text")
            return json.loads(llm_output)

        except json.JSONDecodeError:
            pass  # Try more lenient parsing

    # 4. Attempt to find the first valid JSON object in the string
    match = re.search(r"\{[\s\S]*\}", llm_output)
    if match:
        try:
            #logger.info(f"user id:{user_id}--llm output parsing, Attempt to find the first valid JSON object in the string ")
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            pass #Try more lenient parsing.

    # 5. Attempt to parse the string as a python dictionary, in cases where the LLM does not return a JSON string, but a python dictionary string.
    try:
        #logger.info(f"user id:{user_id}--llm output parsing, Attempt to parse the string as a python dictionary, in cases where the LLM does not return a JSON string, but a python dictionary string.")
        return eval(llm_output)
    except (SyntaxError, NameError, TypeError, json.JSONDecodeError):
        pass

    # 6. If all else fails, return None
    #logger.info(f"user id:{user_id}--llm output parsing, Failed to parse the output as a JSON object or python dictionary.")
    return None

BEARER_TOKEN = "A7x!G2p@Q9#L"

def validate_bearer_token(request, expected_token):
    auth_header = request.headers.get('Authorization', '')
    if not auth_header.startswith('Bearer '):
        return jsonify({"error": "Invalid or missing Authorization header."}), 401
    token = auth_header.split(' ')[1]
    if token != expected_token:
        return jsonify({"error": "Unauthorized. Invalid Bearer token."}), 403
    return None

def load_prompts_into_dataframe(connection):
    """Fetches all context-specific prompts from the database and stores them in a DataFrame."""
    global PROMPT_DATA_FRAME
    if connection:
        cursor = connection.cursor()
        try:
            cursor.execute("SELECT id, system_prompt, user_prompt, sequence FROM alta_filters")
            columns = [desc[0] for desc in cursor.description]
            prompts_data = cursor.fetchall()
            PROMPT_DATA_FRAME = pd.DataFrame(prompts_data, columns=columns)
            print(PROMPT_DATA_FRAME)
            print("Context prompts loaded into DataFrame successfully.")
        except psycopg2.Error as e:
            print(f"Error fetching context prompts for DataFrame: {e}")
            PROMPT_DATA_FRAME = None
        finally:
            cursor.close()
    else:
        print("Database connection not available to load context prompts.")
        PROMPT_DATA_FRAME = None

def fetch_prompt(connection, prompt_id: int, session_id:str |None = None ) -> Optional[Dict[str, str]]:
    global PROMPT_DATA_FRAME
    load_prompts_into_dataframe(connection)
    if PROMPT_DATA_FRAME is not None:
        log_message(connection, 'INFO', 'df is not none',None, session_id)
        try:
            filtered_df = PROMPT_DATA_FRAME[PROMPT_DATA_FRAME['id'] == prompt_id]
            log_message(connection, 'INFO', 'df filtering is done',{"data":str(filtered_df)}, session_id)
            if not filtered_df.empty:
                log_message(connection, 'INFO', 'df filtering is done',{"system_prompt": filtered_df.iloc[0]['system_prompt'],
                    "user_prompt": filtered_df.iloc[0]['user_prompt'],
                    "sequence": int(filtered_df.iloc[0]['sequence'])}, session_id)
                return {
                    "system_prompt": filtered_df.iloc[0]['system_prompt'],
                    "user_prompt": filtered_df.iloc[0]['user_prompt'],
                    "sequence": int(filtered_df.iloc[0]['sequence'])
                }
            else:
                print(f"Prompt with ID {prompt_id} not found in DataFrame.")
                return None
        except KeyError as e:
            print(f"Error accessing columns in DataFrame: {e}")
            return None
    else:
        print("Prompt DataFrame not loaded.")


# --- Modified fetch_core_prompt Function ---
def fetch_core_prompt(connection, session_id: str | None = None) -> Optional[str]:
    CORE_PROMPT_QUERY='''SELECT core_prompt_id, prompt
        FROM contextsense_core_prompt
        ORDER BY core_prompt_id DESC
        LIMIT 1; '''
    if connection:
        cursor = connection.cursor()
        try:
            print("execution yet to happen")
            cursor.execute(CORE_PROMPT_QUERY)
            result = cursor.fetchone()
            print("core prompt db",result)
            if result:
                core_prompt = result[1]
                log_message(connection, 'INFO', 'Successfully fetched core prompt from database', {"core_prompt_id": result[0],"prompt": result[1]}, session_id)
                return core_prompt
            else:
                log_message(connection, 'WARNING', 'Core prompt not found in database',None, session_id)
                return None
        except psycopg2.Error as e:
            log_message(connection, 'ERROR', 'Error fetching core prompt from database', {"error": str(e)}, session_id)
            return None
        finally:
            cursor.close()
    else:
        log_message(connection, 'ERROR', 'Database connection not available to fetch core prompt', None, session_id)
        return None


def sort_prompts_and_values(system_prompts: List[str], user_prompts: List[str],
                            user_defined_values: List[Optional[str]], user_prompt_values: List[Optional[str]],
                            sequences: List[int]) -> tuple[
    List[str], List[str], List[Optional[str]], List[Optional[str]]]:
    #logger.info("Entering sort_prompts_and_values function.")
    #logger.info(f"Length of sequences: {len(sequences)}")
    #logger.info(f"Length of system_prompts: {len(system_prompts)}")
    #logger.info(f"Length of user_prompts: {len(user_prompts)}")
    #logger.info(f"Length of user_defined_values: {len(user_defined_values)}")
    #logger.info(f"Length of user_prompt_values: {len(user_prompt_values)}")

    # Create a list of tuples to sort based on sequence
    #logger.info("Creating combined list of tuples.")
    combined = list(zip(sequences, system_prompts, user_prompts, user_defined_values, user_prompt_values))
    #logger.info(f"Combined list before sorting: {combined}")
    #logger.info(f"Length of combined list: {len(combined)}")

    # Check the length of the first tuple in combined (if it exists)
    if combined:
        print(f"Length of the first tuple in combined: {len(combined[0])}")

    #Sort the combined list based on the sequence (the first element of each tuple)

    combined.sort(key=lambda item: item[0])


    # Unzip the sorted list back into separate lists
    try:
        sorted_sequences, sorted_system_prompts, sorted_user_prompts, sorted_user_defined_values, sorted_user_prompt_values = zip(
            *combined)
    except ValueError as e:
        #logger.error(f"Error during unzipping: {e}. Check if all input lists have the same length when zipped.")
        raise

    #logger.info("Returning sorted lists.")
    return (list(sorted_system_prompts), list(sorted_user_prompts),
            list(sorted_user_defined_values), list(sorted_user_prompt_values))

def secure_xml_wrap(tag_name: str, value: Optional[str]) -> str:
    """
    Wraps user-provided strings in XML tags to prevent prompt injection.
    Handles None types gracefully by returning an empty string.
    """
    if not value:
        return ""
    
    # Strip any attempt by the user to inject a closing tag
    safe_value = str(value).replace(f"</{tag_name}>", "")
    return f"<{tag_name}>{safe_value}</{tag_name}>"

@app.route('/process_context_sense/', methods=['POST'])
def process_context_sense():
    """Main API endpoint for processing context sense."""
    conn = connect_db()  # Get database connection
    if conn is None:
        return jsonify({"error": "Failed to connect to database"}), 500
    session_id=str(uuid.uuid4())

    try:
        log_message(conn, 'INFO', 'Starting /process_context_sense/ request',None,session_id)  # log
        auth_error = validate_bearer_token(request, "A7x!G2p@Q9#L")
        if auth_error:
            log_message(conn, 'ERROR', 'Authentication error', {"error": auth_error[0].json},session_id)  # log
            return auth_error
        try:
            data = TextInput(**request.get_json())
            user_id = data.user_id
            log_message(conn, 'INFO', 'Request data validated',
                        {"user_id": user_id, "request_data": data.model_dump()},session_id)  # log
        except ValidationError as err:
            log_message(conn, 'ERROR', 'Validation error', {"error": err.errors()},session_id)  # log
            return jsonify(err.errors()), 400

        system_prompts: List[str] = []
        user_prompts: List[str] = []
        user_defined_values: List[Optional[str]] = []
        user_prompt_values: List[Optional[str]] = []
        sequence: List[int] = []
        system_prompts1: List[str] = []
        user_defined_values1: List[str] = []
        log_message(conn, 'INFO', 'triggering core_prompt function',None,session_id)
        core_prompt = fetch_core_prompt(conn, session_id)
        log_message(conn, 'INFO', 'core prompt fetched succefully',{"core prompt":core_prompt},session_id)
        if core_prompt is None:
            log_message(conn, 'ERROR', 'Failed to fetch core prompt',
                        {"core_system_prompt_id": data.core_system_prompt_id},session_id)  # log
            return jsonify({"error": "Failed to fetch core prompt"}), 500

        def process_prompts(prompt_id, user_defined_value):
            """Helper function to fetch and process prompts."""
            if prompt_id:
                log_message(conn, 'INFO', 'fetch_prompt API triggered',None,session_id)
                fetched_data = fetch_prompt(conn,prompt_id,session_id)
                log_message(conn, 'INFO', 'fetch_prompt API responded', {"prompt_id": prompt_id, "prompt": fetched_data},session_id)
                if fetched_data:
                    system_prompts1.append(fetched_data["system_prompt"])
                    user_prompts.append(fetched_data["user_prompt"])
                    user_defined_values1.append(user_defined_value)
                    user_prompt_values.append(user_defined_value)
                    sequence.append(fetched_data["sequence"])
                else:
                    user_defined_values1.append("")
                    user_prompt_values.append("")
                    system_prompts1.append("")
                    user_prompts.append("")
                    sequence.append(-1)
                    log_message(conn, 'ERROR', 'Failed to fetch prompt data', {"prompt_id": prompt_id},session_id)  # log
            else:
                system_prompts1.append("")
                user_prompts.append("")
                user_defined_values1.append("")
                user_prompt_values.append("")
                sequence.append(-1)
                log_message(conn, 'INFO', 'Prompt ID was None', {"prompt_id": prompt_id},session_id)  # log

        process_prompts(data.user_context_id, data.user_context_value)
        process_prompts(data.user_tone_id, data.user_tone_value)
        process_prompts(data.user_domain_id, data.user_domain_value)
        process_prompts(data.user_coherence_id, data.user_coherence_value)
        process_prompts(data.user_audience_id, data.user_audience_value)

        system_prompts1, user_prompts, user_defined_values1, user_prompt_values = sort_prompts_and_values(
            system_prompts1, user_prompts, user_defined_values1, user_prompt_values, sequence)
        log_message(conn,'INFO','SORTING IS DONE',{"system prompts":system_prompts1,"user_prompts":user_prompts,"user_defined_values1":user_defined_values1, "user_prompt_values":user_prompt_values},session_id)

        system_prompts.append(core_prompt)
        user_defined_values.append(None)
        system_prompts.extend(system_prompts1)
        
        # openai_key = get_openai_key_from_keyvault()
        token_provider = get_azure_openai_token_provider()
        
        user_defined_values.extend(user_defined_values1)

        formatted_system_prompts = []
        system_prompt_template = PromptTemplate(
            input_variables=["source_language", "target_language", "source_text", "translated_text",
                             "user_defined"],
            template="{}"
        )
        #log_message(conn, 'INFO', 'About to enter for loop for system prompt final edits',None,session_id)

        for prompt, value in zip(system_prompts, user_defined_values):
            system_prompt_template.template = prompt
            safe_user_value = secure_xml_wrap("user_request", value)
            formatted_system_prompts.append(system_prompt_template.format(
                source_language=data.source_language,
                target_language=data.target_language,
                source_text=data.source_text,
                translated_text=data.translated_text,
                user_defined=safe_user_value
            ))
        #log_message(conn, 'INFO', 'exited for loop for system prompt final edits',None,session_id)


        system_prompt_str = "\n".join(formatted_system_prompts)
        #log_message(conn, 'INFO', 'system prompt join operation after for loop is done',None,session_id)


        parser = PydanticOutputParser(pydantic_object=RefinedOutput)
        formatted_system_prompt = system_prompt_str + """
            Output:
            Return ONLY the refined text and an explanation in JSON format.
            format should follow following output format
            """ + parser.get_format_instructions()
        log_message(conn, 'INFO', 'System prompt formatted',
                    {"formatted_system_prompt": formatted_system_prompt},session_id)  # log

        system_message = SystemMessage(content=formatted_system_prompt)

        formatted_user_prompts = []
        human_prompt = PromptTemplate(
            input_variables=["source_language", "target_language", "source_text", "translated_text",
                             "user_defined"],
            template="{}"
        )

        for prompt, value in zip(user_prompts, user_prompt_values):
            human_prompt.template = prompt
            safe_user_value = secure_xml_wrap("user_request", value)
            formatted_user_prompts.append(human_prompt.format(
                source_language=data.source_language,
                target_language=data.target_language,
                source_text=data.source_text,
                translated_text=data.translated_text,
                user_defined=safe_user_value
            ))

        human_message = HumanMessage(content="\n".join(formatted_user_prompts))
        log_message(conn, 'INFO', 'Human prompt formatted', {"human_message": human_message.content},session_id)  # log
        messages = [system_message, human_message]
        log_message(conn, 'INFO', 'Constructed messages for LLM invocation',None,session_id)  # log


        
        # llm = AzureChatOpenAI(
        #     deployment_name=os.getenv("Alta_deployment_name"),
        #     model="gpt-4o",
        #     temperature=0,
        #     openai_api_key=openai_key,
        #     azure_endpoint=os.getenv("Alta_Azure_end_point"),
        #     openai_api_version="2024-05-01-preview",
        # )
        # NEW
        llm = AzureChatOpenAI(
            deployment_name=os.getenv("Alta_deployment_name"),
            model="gpt-5.1",
            temperature=0,
            azure_ad_token_provider=token_provider,
            azure_endpoint=os.getenv("Alta_Azure_end_point"),
            openai_api_version=os.getenv("Alta_api_version")        )
        try:
            log_message(conn, 'INFO', 'LLM invocation triggered', {"llm request data": [m.content for m in messages]},session_id)
            response = llm.invoke(messages)
            log_message(conn, 'INFO', 'LLM invocation successful', {"llm_response": response.content},session_id)  # log
        except Exception as e:
            log_message(conn, 'ERROR', 'LLM invocation failed', {"error": str(e)},session_id)  # log
            return jsonify({"error": f"LLM invocation failed: {e}"}), 500

        try:
            context_sense_dict = {}
            context_sense_dict["refine"] = dynamic_json_parser(response.content, user_id)
            context_sense_dict["prompt"] = {"system_message": formatted_system_prompt,
                                            "human_message": "\n".join(formatted_user_prompts)}
            log_message(conn, 'INFO', 'LLM response parsed', {"parsed_response": context_sense_dict},session_id)  # log

            
            context_sense_dict["debug_azure_endpoint"] = os.getenv("Alta_Azure_end_point") #added this to debug, remove after debugging!!!
            
            
            return context_sense_dict
        except json.JSONDecodeError as e:
            log_message(conn, 'ERROR', 'JSON Decode Error',
                        {"error": str(e), "llm_response": response.content},session_id)  # log
            return jsonify({"error": "LLM returned invalid JSON."}), 500

    except Exception as e:
        log_message(conn, 'ERROR', 'An unexpected error occurred', {"error": str(e)},session_id)  # log
        return jsonify({"error": f"An unexpected error occurred. Please check the server logs.{e}"}), 500
    finally:
        if conn:
            conn.close()  # Close the database connection in a finally block

if __name__ == '__main__':
    app.run(debug=True)


