from flask import Flask, request, jsonify, render_template
import pandas as pd

app = Flask(__name__)

# Allowed file extensions
ALLOWED_EXTENSIONS = {'csv', 'tsv'}

# Function to check allowed file extension
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# Route for file upload
# @app.route('/upload', methods=['GET', 'POST'])
def upload_file():
    if request.method == 'POST':
        # Check if the file is in the request
        if 'file' not in request.files:
            return jsonify({"message": "No file part"}), 400
        
        file = request.files['file']
        
        # Check if a file is selected
        if file.filename == '':
            return jsonify({"message": "No file selected"}), 400

        # Validate file extension
        if file and allowed_file(file.filename):
            # Determine delimiter based on file extension
            delimiter = ',' if file.filename.endswith('.csv') else '\t'
            try:
                # Read file into a DataFrame
                df = pd.read_csv(file, delimiter=delimiter)
            except Exception as e:
                return jsonify({"message": f"File format error: {str(e)}"}), 400

            # Check for leading or trailing whitespaces
            whitespace_issues = []
            for row_idx, row in df.iterrows():
                for col_idx, (col_name, value) in enumerate(row.items()):
                    if isinstance(value, str):
                        stripped_value = value.strip()
                        if value != stripped_value:  # Check for leading/trailing spaces
                            issue = {
                                "row": row_idx + 1,  # Adjust for 1-based indexing
                                "column": col_name,
                                "original_value": value
                            }
                            whitespace_issues.append(issue)
            
            if whitespace_issues:
                return jsonify({
                    "message": "File contains leading or trailing whitespaces.",
                    "issues": whitespace_issues
                }), 400
            else:
                return jsonify({"status":"Success",
                                "message": "File is as per the requirements of a Glossary File"}), 200
        
        else:
            return jsonify({"message": "Invalid file type. Only CSV and TSV files are allowed."}), 400

    # Render a basic form for file upload
    return '''
    <!doctype html>
    <title>Upload a File</title>
    <h1>Upload a CSV or TSV File</h1>
    <form method=post enctype=multipart/form-data>
      <input type=file name=file>
      <input type=submit value=Upload>
    </form>
    '''

if __name__ == '__main__':
    app.run(debug=True)
