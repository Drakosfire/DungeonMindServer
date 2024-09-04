# This imports the code from files and modules
from flask import Flask, request, jsonify, send_from_directory, url_for, render_template, send_file
from flask_cors import CORS 
import os
import ctypes
from storegenerator import store_helper as sh
from storegenerator import block_builder
from storegenerator import sd_generator as sd

# This is a fix for the way that python doesn't release system memory back to the OS and it was leading to locking up the system
libc = ctypes.cdll.LoadLibrary("libc.so.6")
M_MMAP_THRESHOLD = -3

# Set malloc mmap threshold.
libc.mallopt(M_MMAP_THRESHOLD, 2**20)

# Initialize the Flask application
app = Flask(__name__)
os.makedirs('storegenerator/static/images', exist_ok=True)

# Serve DungeonMind static files
@app.route('/static/<path:filename>')
def dungeonmind_static(filename):
    return send_from_directory('static', filename)

# Serve storegenerator static files
@app.route('/storegenerator/static/<path:filename>')
def storegenerator_static(filename):
    return send_from_directory(os.path.join('storegenerator', 'static'), filename)


# Serve HTML files from the main directory
@app.route('/storegenerator/<path:filename>')
def serve_html(filename):
    return send_from_directory('.', filename)

@app.after_request
def apply_headers(response):
    response.headers["Cross-Origin-Opener-Policy"] = "same-origin-allow-popups"
    return response

# Route to serve the landing page at the root URL
@app.route('/')
def landing_page():
    return send_from_directory('static', 'index.html')

@app.route('/storegenerator/')
def storegenerator():
    css_files = {
        'all_css': url_for('storegenerator_static', filename='all.css'),
        'font_css': url_for('storegenerator_static', filename='css.css?family=Open+Sans:400,300,600,700'),
        'bundle_css': url_for('storegenerator_static', filename='bundle.css'),
        'style_css': url_for('storegenerator_static', filename='style.css'),
        'phb_style_css': url_for('storegenerator_static', filename='5ePHBstyle.css'),
        'store_ui_css': url_for('storegenerator_static', filename='storeUI.css')
    }
    return render_template('storeUI.html', css_files=css_files)

CORS(app)

# Route to handle the incoming POST request with user description
@app.route('/process-description', methods=['POST'])
def process_description():
    data = request.json  # Get the JSON data from the request
    user_input = data.get('user_input', '')  # Extract the 'user_input' field
    # Print the received input to the console
    print(f"Received user input: {user_input}")
    # Call the LLM with the user input and return the result
    llm_output = sh.call_llm_and_cleanup(user_input)
    processed_blocks = block_builder.build_blocks(llm_output, block_builder.block_id)

    return jsonify({'html_blocks': processed_blocks})  # Return the LLM output as JSON

@app.route('/generate-image', methods=['POST'])
def generate_image():
    data = request.get_json()
    image_subject = data.get('store_name')
    sd_prompt = data.get('sd_prompt')
    image_subject_name = data.get('store_front_sd_prompt')

    if not sd_prompt:
        return jsonify({'error': 'Missing sd_prompt'}), 400
    image_subject = data.get('image_subject')
    if not sd_prompt:
        return jsonify({'error': 'Missing sd_prompt'}), 400

    try:
        image_url = sd.preview_and_generate_image(image_subject, image_subject_name, sd_prompt)
        return jsonify({'image_url': image_url})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=7860, debug=True)  # Run the app on localhost, port 7860

