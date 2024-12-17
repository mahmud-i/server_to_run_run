from flask import Flask, render_template, request, jsonify, redirect, url_for, flash, render_template
from configparser import ConfigParser
import os
import datetime
import subprocess
import queue
import threading
import uuid


app = Flask(__name__)
app.secret_key = 'your_secret_key'

def datetime_now():
    date = datetime.datetime.now().strftime("%m_%d_%y")
    time = datetime.datetime.now().strftime("%H_%M")
    return date, time

server_config_path = "config_server.ini"
config_server = ConfigParser()
config_server.read(server_config_path)

python_path = config_server['paths'].get('python_path')
regression_project_drive = config_server['paths'].get('regression_project_drive')
regression_project_dir = config_server['paths'].get('regression_project_dir')
regression_project_path = config_server['paths'].get('regression_project_path')

run_server_project_base = config_server['paths'].get('run_server_project_base')
print(f"Project base: {run_server_project_base}")

# Directory for storing brand config files
config_dir = config_server['paths'].get('config_files_directory')
print(f"Config directory: {config_dir}")

test_run_base = config_server['test_run'].get('test_run_base')


@app.route('/')
def home():
    return render_template('home.html')


@app.route('/create_brand_config', methods=['GET', 'POST'])
def create_brand_config():
    if request.method == 'POST':
        data = request.json
        brand_name = data.get('brand_name')

        # Create the brand config file in INI format
        config = ConfigParser()

        # Add URLs data section
        config['urls_data'] = {
            'prod_domain_url': data.get('prod_domain_url', ''),
            'csv_file_path': data.get('csv_file_path', ''),
            'urls_list': data.get('urls_list', '')
        }

        # Add testing data directory section
        config['testing_data_directory'] = {
            'data_directory': data.get('data_directory', '')
        }

        # Add integration check section
        config['integration_check'] = {
            'ucu_slug': data.get('ucu_slug', ''),
            'contact-us': data.get('contact_us', ''),
            'faq': data.get('faq', ''),
            'dsar_text': data.get('dsar_text', '')
        }

        # Write the configuration to an INI file
        config_file_path = os.path.join(config_dir, f"{brand_name}.ini")
        with open(config_file_path, 'w') as configfile:
            config.write(configfile)

        return jsonify({"message": "Brand configuration created successfully!"}), 201

    return render_template('create_brand_config.html')


def check_config(brand_name):
    """Check if the brand configuration file exists and return its content."""
    config_file_path = f"{config_dir}/{brand_name}.ini"

    print(f"Config file path: {config_file_path}")

    if os.path.exists(config_file_path):
        config = ConfigParser()
        config.read(config_file_path)

        print(f"{config.sections()}")

        return {"exists": True, "data": {s: dict((config.items(s))) for s in config.sections()}}
    else:
        print("Brand configuration not found.")
        return {"exists": False, "message": "Brand configuration not found."}


@app.route('/check_brand_config/<string:brand_name>', methods=['GET'])
def check_brand_config(brand_name):
    result = check_config(brand_name)
    return jsonify(result), 200


@app.route('/view_brand_config', methods=['GET'])
def view_brand_config():
    """Render the HTML page for checking and editing brand configuration."""
    return render_template('view_brand_config.html')


@app.route('/save_config/<string:brand_name>', methods=['POST'])
def save_config(brand_name):
    data = request.json
    content = data.get('content', {})

    # Convert JSON data to INI format
    config_file_path = os.path.join(config_dir, f"{brand_name}.ini")
    os.makedirs(config_file_path, exist_ok=True)
    config = ConfigParser()

    # Populate the ConfigParser with the JSON data
    for section, values in content.items():
        config[section] = {}
        for key, value in values.items():
            config[section][key] = str(value)  # Ensure all values are strings

    try:
        # Write the INI file
        with open(config_file_path, 'w') as configfile:
            config.write(configfile)

        return jsonify({"message": "Configuration updated successfully!"}), 200
    except Exception as e:
        return jsonify({"message": f"Brand configuration not found. {e}"}), 404


@app.route('/run_test', methods=['GET', 'POST'])
def run_test():
    if request.method == 'POST':
        # Retrieve test parameters from the request
        brands = request.form.get('brands')
        env = request.form.get('env')
        headless_chk = request.form.get('headless_chk')
        full_site_testing = request.form.get('full_site_testing')
        parsing_method = request.form.get('parsing_method','3')

        # Check brand configuration availability before running tests
        brand_availability = check_config(brands)
        if not brand_availability['exists']:
            return jsonify({"message": brand_availability['message']}), 404

        # Create a new INI file for test run configuration
        test_config = ConfigParser()

        # Add settings section
        test_config['settings'] = {
            'brands': brands,
            'env': env,
            'headless_chk': headless_chk,
            'full_site_testing': full_site_testing,
            'parsing_method': parsing_method
        }

        # Add platform section
        test_config['platform'] = {
            'browser_type': request.form.get('browser_type', 'chromium'),
            'viewport_width': request.form.get('viewport_width', '1900'),
            'viewport_height': request.form.get('viewport_height', '960'),
            'mobile_emulation': request.form.get('mobile_emulation', 'N'),
            'mobile_model': request.form.get('mobile_model', 'iPhone 14 Pro')
        }

        tests = request.form.getlist('tests')  # Get list of checked values
        tests_string = ', '.join(tests)  # Join them into a single string

        test_config['tests'] = {
            'tests_to_run': tests_string
        }

        date, time = datetime_now()
        test_run_config_dir = f"{test_run_base}/{date}/{time}"
        test_run_report_dir = f"{test_run_config_dir}/Tests_result_&_data"

        # Directory for storing test run configuration files
        os.makedirs(test_run_config_dir, exist_ok=True)
        test_run_config_file = f"{test_run_config_dir}/test_run_config.ini"

        # Write the test run configuration to an INI file
        with open(test_run_config_file, 'w') as configfile:
            test_config.write(configfile)

        # Logic to run tests based on the parameters can be added here
        message_queue = queue.Queue()
        def execute_test():
            try:
                commands = [
                    "echo 'Running tests...'",
                    f"{regression_project_drive}",
                    f"cd {regression_project_dir}",
                    f"python {regression_project_path} --config \"{test_run_config_file}\" --reportpath \"{test_run_report_dir}\""
                ]

                # Run the command and capture output
                for command in commands:
                    print(f"Executing: {command}")
                    result = subprocess.run(command, shell=True, text=True, capture_output=True)
                    print("Output:")
                    print(result.stdout)
                    message_queue.put(("info", result.stdout))
                    if result.stderr:
                        print("Error:")
                        print(result.stderr)
                        message_queue.put(("danger", f"Test failed with error: {result.stderr}"))

                message_queue.put(("success", "Test completed successfully!"))
                #message_queue.put(("info", result.stdout))  # Optional: capture the stdout

            except Exception as e:
                message_queue.put(("danger", f"Error while running the test: {str(e)}"))

        thread = threading.Thread(target=execute_test)
        thread.start()

        # Check for messages in the queue after starting the thread
        thread.join()  # Wait for the thread to finish

        while not message_queue.empty():
            category, message = message_queue.get()
            flash(message, category)
            return jsonify({"message": "Tests executed successfully!", "project_output": [f"{message}", f"{category}"] }), 200

    return render_template('run_test.html')


if __name__ == '__main__':
    app.run(debug=True)