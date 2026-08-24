


import os
from datetime import datetime, timedelta

import pandas as pd
import psycopg2
from psycopg2.extras import RealDictCursor
from flask import Flask, request, jsonify

app = Flask(__name__)

# -----------------------------
# Database configuration
# -----------------------------
DB_CONFIG = {
    "dbname": os.getenv("DB_NAME"),
    "user": os.getenv("DB_USER"),
    "password": os.getenv("DB_PASSWORD"),
    "host": os.getenv("DB_HOST"),
    "port": os.getenv("DB_PORT")
}


def connect_db():
    try:
        return psycopg2.connect(**DB_CONFIG)
    except Exception as e:
        print(e)
        return None


def fetch_data(query):
    conn = connect_db()

    if conn is None:
        return None

    try:
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        cursor.execute(query)
        return cursor.fetchall()

    finally:
        conn.close()



@app.route("/translation_metrics", methods=["POST"])
def translation_metrics():

    body = request.get_json()
    filter_type = body.get("filter")

    excluded_users = [
        'Vinayak Inamadar', 'Chanbasava Koti', 'Sherlock5', 'Jain, Anshuman',
        'Sachin Bhusanurmath', 'Dinesh Rout', 'Santosh Sohani', 'Bharatkumar Salalli',
        'Vinayak Inamadhar', 'Harsh Aneppanavar', 'Nseke, Welly', 'Gaston Chan',
        'Test User', 'Raqib Rasheed', 'Nadeem, Pervez', 'Yuan, Jon', 'McHale, Peter'
    ]

    doc_query = "SELECT * FROM user_docu_trans_log"
    text_query = "SELECT * FROM user_text_trans_log"

    doc_data = fetch_data(doc_query)
    text_data = fetch_data(text_query)

    if doc_data is None or text_data is None:
        return jsonify({"error": "Unable to fetch data"}), 500

    df_doc = pd.DataFrame(doc_data)
    df_text = pd.DataFrame(text_data)

    if len(df_doc) == 0:
        return jsonify({"error": "No document records found"}), 404
    if len(df_text) == 0:
        return jsonify({"error": "No text records found"}), 404

    # Normalize billed_characters to numeric (doc table stores it as string)
    df_doc["billed_characters"] = pd.to_numeric(df_doc["billed_characters"], errors="coerce").fillna(0)
    df_text["billed_characters"] = pd.to_numeric(df_text["billed_characters"], errors="coerce").fillna(0)

    # Convert timestamps
    df_doc["date_and_time"] = pd.to_datetime(df_doc["date_and_time"])
    df_text["date_and_time"] = pd.to_datetime(df_text["date_and_time"])

    # Remove excluded users
    df_doc = df_doc[~df_doc["user"].isin(excluded_users)]
    df_text = df_text[~df_text["user"].isin(excluded_users)]

    df_all = pd.concat([df_doc, df_text], ignore_index=True)

    # --------------------------
    # Date Filtering
    # --------------------------
    today = datetime.now()

    if filter_type == "last_1_day":
        start_date = today - timedelta(days=1)
        end_date = None

    elif filter_type == "last_7_days":
        start_date = today - timedelta(days=7)
        end_date = None

    elif filter_type == "last_30_days":
        start_date = today - timedelta(days=30)
        end_date = None

    elif filter_type == "custom_range":
        try:
            start_date = datetime.strptime(body["from_date"], "%d:%m:%Y")
            end_date = datetime.strptime(body["to_date"], "%d:%m:%Y") + timedelta(days=1)
        except Exception:
            return jsonify({"error": "Date format should be dd:mm:yyyy"}), 400

    else:
        return jsonify({"error": "Invalid filter"}), 400

    if end_date is None:
        filtered_doc = df_doc[df_doc["date_and_time"] >= start_date]
        filtered_all = df_all[df_all["date_and_time"] >= start_date]
    else:
        filtered_doc = df_doc[
            (df_doc["date_and_time"] >= start_date) & (df_doc["date_and_time"] < end_date)
        ]
        filtered_all = df_all[
            (df_all["date_and_time"] >= start_date) & (df_all["date_and_time"] < end_date)
        ]

    # --------------------------
    # KPIs scoped to selected period only
    # --------------------------
    documents_translated = len(filtered_doc)
    unique_documents_translated = filtered_doc["document_name"].nunique()
    characters_translated = int(filtered_all["billed_characters"].sum())

    vendor_documents = (
        filtered_doc.groupby("vendor")["document_name"]
        .count()
        .to_dict()
    )

    vendor_characters = (
        filtered_all.groupby("vendor")["billed_characters"]
        .sum()
        .to_dict()
    )

    response = {
        "selected_period": filter_type,
        "documents_translated": documents_translated,
        "unique_documents_translated": unique_documents_translated,
        "characters_translated": characters_translated,
        "documents_per_vendor": vendor_documents,
        "characters_per_vendor": vendor_characters,
    }

    return jsonify(response)


if __name__ == "__main__":
    app.run(debug=True)




