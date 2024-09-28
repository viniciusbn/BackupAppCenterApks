import requests
import os
import boto3
import time
import hashlib
import csv
import sys
import argparse
import shutil
from datetime import datetime
from botocore.exceptions import ClientError, NoCredentialsError, PartialCredentialsError, ProfileNotFound, TokenRetrievalError, ParamValidationError
from tenacity import retry, stop_after_attempt, wait_exponential, RetryError
from variables import *

# Set the headers for the API request to App Center
headers = {
    'X-API-Token': API_TOKEN,
    'Accept-Encoding': 'gzip, deflate'
}

# Argument parser to accept command line arguments
parser = argparse.ArgumentParser()
parser.add_argument('-s', '--storage', type=str, help='Where to store the files locally or in AWS S3 (local or AWS S3).', default='local', choices=['local', 's3'])
parser.add_argument('-p', '--preserve', action='store_true', help='Preserve the original APK files in the local directory if storage is set to AWS S3.', default=False)
parser.add_argument('-y', '--yes', action='store_true', help='Automatically answer "yes" to all prompts.', default=False)
# Parse the arguments
args = parser.parse_args()

# Function to calculate the MD5 hash
def calculate_md5_hash(file_path, chunk_size=8192):
    md5 = hashlib.md5()
    with open(file_path, 'rb') as file:
        chunk = file.read(chunk_size)
        while chunk:
            md5.update(chunk)
            chunk = file.read(chunk_size)
    return md5.hexdigest()

# Function to download the file from App Center
def download_file(release_download_url, file_path, release_md5_fingerprint):
    # Check if the file already exists and verify its MD5 hash before downloading
    if os.path.exists(file_path):
        md5_hash = calculate_md5_hash(file_path)
        if md5_hash == release_md5_fingerprint:
            print(f'File already downloaded: {file_path}')
            status = 'Cached'
            attempt = 0
            return status, attempt, md5_hash
    else:
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
    attempt = 1
    # Attempt to download the APK file up to DOWNLOAD_MAX_ATTEMPTS times with a delay of 1 second between attempts.
    print(f'Downloading file...')
    while attempt <= DOWNLOAD_MAX_ATTEMPTS:
        # Download the APK file
        response = requests.get(release_download_url, stream=True)
        with open(file_path, 'wb') as file:
            for chunk in response.iter_content(chunk_size=8192):
                file.write(chunk)        
        # Calculate the MD5 hash of the downloaded file
        md5_hash = calculate_md5_hash(file_path)
        # Check if the local MD5 hash matches the App Center MD5 hash
        if md5_hash == release_md5_fingerprint:
            print(f'File downloaded successfully: {file_path}')
            status = 'Success'
        else:
            # If the hashes do not match, the download failed
            print(f'Download failed. Attempt {attempt + 1}/{DOWNLOAD_MAX_ATTEMPTS}')
            attempt += 1
            status = 'Failed'
            time.sleep(1)
        return status, attempt, md5_hash

# Function to connect to AWS
def connect_to_aws():
    try:
        # If AWS_PROFILE is defined, use it
        if AWS_PROFILE:
            print(f"Using AWS profile {AWS_PROFILE} defined in the variables.py file.")
            session = boto3.Session(profile_name=AWS_PROFILE)
        # If AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY are defined, use them
        elif AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY and AWS_REGION:
            print("Using AWS credentials defined in the variables.py file.")
            session = boto3.Session(aws_access_key_id=AWS_ACCESS_KEY_ID, aws_secret_access_key=AWS_SECRET_ACCESS_KEY, region_name=AWS_REGION, aws_session_token=AWS_SESSION_TOKEN)
        else:
            print("No AWS credentials or profile provided. Check your variables.py file.")
            sys.exit()
        # Simple check if the AWS connection was successful
        s3_client = session.client('s3')
        s3_client.list_buckets()
        print("Connected to AWS successfully.")
        return s3_client
    # Error handling for AWS connection
    except TokenRetrievalError as e:
        print(f"Failed to refresh SSO token: {e}")
        print(f"Please run 'aws sso login --profile {AWS_PROFILE}' to refresh your SSO token manually.")
    except (NoCredentialsError, PartialCredentialsError):
        print("AWS connection failed. Please check your AWS credentials in the variables.py file.")
    except ProfileNotFound:
        print("AWS profile not found. Please check your AWS profile configuration or variables.py file.")
    except ClientError as e:
        print(f"Failed to connect to AWS: {e}")
    sys.exit()

# Function to check if the bucket exists
def check_bucket_exists(s3_client, bucket_name):
    try:
        # Check if the bucket exists
        s3_client.head_bucket(Bucket=bucket_name)
        print(f'Files will be stored in the bucket: {AWS_BUCKET_NAME}')
        return True
    # Error handling for bucket check
    except ParamValidationError as e:
        print(f"Invalid or null bucket name.")
        print(f'\n{e}')
        sys.exit()
    except ClientError as e:
        error_code = e.response['Error']['Code']
        if error_code == '404' or error_code == '403':
            print("Bucket not found or access denied. Check the bucket name in the variables.py file.")
        else:
            print(f"Error checking the bucket: {e}")
        sys.exit()

def check_s3_object_exists(s3_client, bucket_name, object_key, md5_hash):
    try:
        response = s3_client.head_object(Bucket=bucket_name, Key=object_key)
        s3_md5 = response['ETag'].strip('"')
        if s3_md5 == md5_hash:
            return 'Cached'
    except s3_client.exceptions.ClientError as e:
        error_code = e.response['Error']['Code']
        if error_code == '404':
            return False
        else:
            raise

# Function to upload the file to AWS S3
def upload_file_to_s3(s3_client, file_path, bucket_name, object_key, md5_hash, succes_message):
    # Upload the file to AWS S3
    try:
        status = check_s3_object_exists(s3_client, bucket_name, object_key, md5_hash)
        attempt = 0
        status = 'Not Started'
        # Will upload the file until it is successful or the maximum number of attempts is reached
        while attempt < UPLOAD_MAX_ATTEMPTS:
            if status == 'Not Started' or status == 'Failed':
                # Upload the file
                s3_client.put_object(Bucket=bucket_name, Key=object_key, Body=open(file_path, 'rb'))
                response = s3_client.head_object(Bucket=bucket_name, Key=object_key)
                s3_md5 = response['ETag'].strip('"')
                # Check if the local and S3 MD5 hash matches
                if s3_md5 == md5_hash:
                    status = 'Success'
                    if succes_message:
                        print(succes_message)
                    break
                # If the hashes do not match, the upload failed
                else:
                    print(f'Failed to upload to S3: {bucket_name}/{object_key}')
                    status = 'Failed'
                    attempt += 1
                    time.sleep(1)
        return status
    # Error handling for S3 upload
    except ClientError as e:
        print(f"Error uploading file: {e}")
        return 'Failed'

# Retry settings: stop after 5 attempts, wait exponentially between retries (e.g., 1s, 2s, 4s, ...)
@retry(stop=stop_after_attempt(5), wait=wait_exponential(multiplier=1, min=1, max=10))
def make_request(url, headers):
    response = requests.get(url, headers=headers)
    if response.status_code != 200:
        raise Exception(f"Request failed with status code {response.status_code}")
    return response

# Function to ask the user for confirmation        
def user_confirmation(message):
    # If the yes flag is set, return True
    if args.yes:
        return True
    # Otherwise, ask the user for confirmation
    else:
        response = input(f'\n{message}: ').strip().lower()
        if response == 'yes':
            return True
        elif response == 'no':
            return False
        else:
            print("Invalid response. Please enter 'yes' or 'no'.")
            # Attempt to ask again
            return user_confirmation()

# Ask the user to confirm proceeding with execution
if user_confirmation("Do you want to proceed?"):
    print("Proceeding with execution...")
else:
    print("Execution halted by the user.")
    sys.exit()

# Function to generate the report file
report_file = f"{WORKDIR}/REPORT_{datetime.now().strftime('%m-%d-%Y_%H-%M-%S')}.csv"
report_file_name = os.path.basename(report_file)
def update_report_file(row,message):
    # Create the folder if it doesn't exist and open the log file
    os.makedirs(os.path.dirname(report_file), exist_ok=True)
    # Open the log file and write the header
    with open(report_file, 'a', encoding='utf-8', newline='') as file:
        writer = csv.writer(file)
        writer.writerow(row)
    print(f'\n{message}: {report_file_name}\n')

update_report_file(['timestamp', 'app_name', 'release_id', 'release_version', 'release_download_url', 'download_atempt', 'download_status', 'upload_status', 'release_md5_fingerprint'],'Report file was created: ')

# Main function to list all apps, releases, and download APK files from the App Center API and upload them to S3 if necessary.
def main():
    try:
        # Print separator for better readability.
        if args.storage == 's3':
            # Store AWS session in s3_client variable
            s3_client = connect_to_aws()
            check_bucket_exists(s3_client, AWS_BUCKET_NAME)
        print('-' * 40)
        # List all apps in the organization using the App Center API.
        response_app_list = make_request(f'{URL_BASE}/apps', headers=headers)
        # Check if the API call was successful.
        if response_app_list.status_code == 200:
            # Get the list of apps.
            list_apps = response_app_list.json()
            if APP_FILTER:
                # Filter apps based on the APP_FILTER list.
                filtered_apps = [app for app in list_apps if app.get('name') in APP_FILTER]
                list_apps = filtered_apps
            for app in list_apps:
                #app_name = app.get('name')
                app_name = app['name']
                # List all releases for the app using the App Center API.
                list_releases = make_request(f'{URL_BASE}/apps/{ORG_NAME}/{app_name}/releases', headers=headers).json()
                for release in list_releases:
                    # Get release details: ID, version, download URL, and MD5 fingerprint.
                    release_id = release['id']
                    release_version = release['short_version']
                    release_more_info = make_request(f'{URL_BASE}/apps/{ORG_NAME}/{app_name}/releases/{release_id}', headers=headers).json()
                    release_download_url = release_more_info['download_url']
                    release_md5_fingerprint = release_more_info['fingerprint']
                    release_date = datetime.strptime(release_more_info['uploaded_at'], '%Y-%m-%dT%H:%M:%S.%fZ').strftime('%Y-%m-%d')
                    release_notes = release_more_info.get('release_notes', 'No release notes available')
                    # Print release details
                    print(f'App name: {app_name}')
                    print(f'Release ID: {release_id}')
                    print(f'Release version: {release_version}')
                    print(f'Release date: {release_date}')
                    print(f'Release download URL: {release_download_url}')
                    print(f'MD5 fingerprint: {release_md5_fingerprint}')
                    print(f'Release release notes:\n{release_notes}')
                    timestamp = datetime.now().strftime('%m/%d/%Y %H:%M:%S')
                    base_folder = get_base_folder(app_name, release_date, release_id, release_version)
                    apk_file_path = f'{WORKDIR}/{base_folder}/{app_name}_v{release_version}.apk'
                    releasenote_file_path = f'{WORKDIR}/{base_folder}/RELEASE_NOTES.txt'
                    os.makedirs(os.path.dirname(releasenote_file_path), exist_ok=True)
                    # If S3 storage is set, check if the file already exists in S3 and validate the MD5 fingerprint, skipping the download if valid.
                    if args.storage == 's3':
                        s3_object_key_apk = f'{base_folder}/{app_name}_v{release_version}.apk'
                        s3_object_key_release_notes = f'{base_folder}/RELEASE_NOTES.txt'
                        if check_s3_object_exists(s3_client, AWS_BUCKET_NAME, s3_object_key_apk, release_md5_fingerprint) == "Cached":
                            print(f'File already exists in S3 with a matching MD5 fingerprint, skipping download and upload: {AWS_BUCKET_NAME}/{s3_object_key_apk}')
                            download_status = 'Skipped'
                            download_attempt = 0
                            upload_status = 'Cached'
                        else:
                            download_status, download_attempt, md5_hash = download_file(release_download_url, apk_file_path, release_md5_fingerprint)
                            upload_status = upload_file_to_s3(s3_client, apk_file_path, AWS_BUCKET_NAME, s3_object_key_apk, md5_hash, f'File successfully uploaded to S3: {AWS_BUCKET_NAME}/{s3_object_key_apk}')
                            print(f'Release notes will be saved in {releasenote_file_path}')
                            with open(releasenote_file_path, 'w', encoding='utf-8') as file:
                                file.write(release_notes)
                            upload_file_to_s3(s3_client, releasenote_file_path, AWS_BUCKET_NAME, s3_object_key_release_notes, calculate_md5_hash(releasenote_file_path), f'Release notes uploaded to S3: {AWS_BUCKET_NAME}/{s3_object_key_release_notes}')    
                        if upload_status == 'Success' and args.preserve == False:
                            os.remove(apk_file_path)
                        # Upload the current log file to S3.
                        s3_object_key_log = f'{report_file_name}'
                        upload_file_to_s3(s3_client, report_file, AWS_BUCKET_NAME, s3_object_key_log, calculate_md5_hash(report_file), "")
                    else:
                        download_status, download_attempt, md5_hash = download_file(release_download_url, apk_file_path, release_md5_fingerprint)
                        upload_status = 'Local'
                        print(f'Release notes will be saved in {releasenote_file_path}')
                        with open(releasenote_file_path, 'w', encoding='utf-8') as file:
                            file.write(release_notes)
                    update_report_file([timestamp, app_name, release_id, release_version, release_download_url, download_attempt, download_status, upload_status, release_md5_fingerprint], f'Report file was updated: ')
                    # Print separator for better readability.
                    print('-' * 40)
            if args.storage == 's3':
                # Upload the final log file to S3.
                s3_object_key_log = f'{report_file_name}'
                upload_file_to_s3(s3_client, report_file, AWS_BUCKET_NAME, s3_object_key_log, calculate_md5_hash(report_file), f'Log file uploaded to S3: {AWS_BUCKET_NAME}/{s3_object_key_log}')
                # If --preserve is not set, ask the user if they want to delete all local files except the log file.
                if args.preserve == False:
                    # Ask the user if they want to delete all local files except the log file.
                    if user_confirmation("Do you want to delete all local files except the log file?"):
                        for item in os.listdir(WORKDIR):
                            path = os.path.join(WORKDIR, item)
                            if item != report_file_name:
                                if os.path.isfile(path):
                                    os.remove(path)
                                elif os.path.isdir(path):
                                    shutil.rmtree(path)
                        print("Local files deleted...")
                else:
                    print("All files are stored in S3. Local files were not deleted.")
            else:
                print("Files stored locally.")
    except KeyboardInterrupt:
        print("Execution halted by the user.")
        sys.exit()

if __name__ == "__main__":
    main()