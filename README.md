# APK Backup and Upload Utility for AppCenter

## Overview

This app was developed to make a backup for APKs from Microsoft AppCenter to AWS S3, for archive purposes.
This utility downloads APK files from App Center and uploads them to an S3 bucket if necessary. It also maintains a log of the operations performed, including download attempts, upload status, and file integrity checks.

## Key Features

1. **List All Apps and Releases**: List all apps and their respective releases from App Center, with the ability to filter specific apps using `APP_FILTER`.
2. **Download APK Files**: Download APK files from the specified releases on App Center, validating the MD5 checksum for file integrity.
3. **Check Files in S3**: Check if files already exist in the specified S3 bucket and validate their MD5 fingerprints to avoid duplicate uploads.
4. **Upload APK Files and Logs to S3**: Upload APK files and logs to an S3 bucket with retry logic for failed uploads.
5. **Optionally Delete Local Files**: After successful uploads to S3, local files can be optionally deleted, unless the `--preserve` option is set.
6. **Preserve Local Files**: Option to preserve local files after uploading to S3 using the `--preserve` parameter.
7. **Customizable Download and Upload Attempts**: Configure the maximum number of attempts for downloading APKs and uploading them to S3 with `DOWNLOAD_MAX_ATTEMPTS` and `UPLOAD_MAX_ATTEMPTS`.
8. **Automatic Confirmation**: Skip manual confirmations using the `-y` flag for a fully automated execution.
9. **Detailed Reporting**: Generate a CSV report containing information about app name, release ID, version, download URL, and the status of both download and upload operations.

## Requirements

- Python 3.x
- pip
- `requests` library
- `boto3` library
- `tenacity`library
- AWS credentials
- App Center API token

## Installation

1. Clone the repository:

    ```bash
    gh repo clone viniciusbn/BackupAppCenterApks
    cd BackupAppCenterApks
    ```

2. Install the required Python packages:

    ```bash
    pip install -r requirements.txt
    ```

    or

    ```bash
    python3 -m pip install -r requirements.txt
    ```


3. Configure your AWS credentials and App Center API token in the configuration section below.

## Configuration

Copy the file `variables.py.example` to `variables.py` and set your configurations:

- `URL_BASE`: Base URL for the App Center API.
- `API_TOKEN`: Token for the App Center API.
- `ORG_NAME`: Organization name in the App Center.
- `APP_FILTER`: List of specific app names to filter or leave it blank.
- `WORKDIR`: Local working directory local storage or for temporary files when files are copied to S3.
- `get_base_folder`: Function to easily manipulate the base folder structure.
- `DOWNLOAD_MAX_ATTEMPTS`: Maximum number of download attempts.
- `UPLOAD_MAX_ATTEMPTS`: Maximum number of upload attempts.
- `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_SESSION_TOKEN`, `AWS_REGION`: AWS credentials.
- `AWS_BUCKET_NAME`: S3 bucket name.
- `AWS_PROFILE`: AWS profile name if you are using AWS profiles.

## Usage

1. **Run the script:**

    ```bash
    python BackupApks.py
    ```

2. **Optional Arguments:**

    - `-s \ --storage s3`: Enable uploading files to S3.
    - `-s \ --storage local`: Enable only local store for apks.
    - `-p \ --preserve`: When --storage s3 was set, optionally keep local files after a successful upload..
    - `-y \ --yes`: No confirmation to start the app.

## Example

This example will upload APKs to the S3 bucket and delete each local file when successfully uploaded.

```bash
python BackupApks.py -s s3
```

This example will store APKs locally without uploading to S3.

```bash
python BackupApks.py -s local
```

This example will upload APKs to the S3 bucket and preserve local files after a successful upload.

```bash
python BackupApks.py -s s3 -p
```

This example will run the script without asking for confirmation to start.

```bash
python BackupApks.py -y
```
