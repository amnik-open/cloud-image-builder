# This script is used for uploading images to distribution dir on object storage

import logging
import os
import sys
import threading
from typing import Optional
import hashlib
import boto3
from boto3.s3.transfer import TransferConfig
from botocore.exceptions import ClientError


def calculate_multipart_etag(source_path, chunk_size):
    """
    This function used for calculating etag of file

    :param source_path: file path to calculate md5
    :param chunk_size: size for each part of file
    :return etag value file
    """
    md5s = []

    with open(source_path, 'rb') as file:
        while True:

            data = file.read(chunk_size)
            if not data:
                break
            md5s.append(hashlib.md5(data))
    if len(md5s) > 1:
        digests = b"".join(m.digest() for m in md5s)
        new_md5 = hashlib.md5(digests)
        new_etag = f'"{new_md5.hexdigest()}-{len(md5s)}"'
    elif len(md5s) == 1:  # file smaller than chunk size
        new_etag = f'"{md5s[0].hexdigest()}"'
    else:  # empty file
        new_etag = '""'

    return new_etag


# Configure logging
logging.basicConfig(level=logging.INFO)

# S3 client instance
s3_client = boto3.client(
    's3',
    endpoint_url=os.getenv("s3_endpoint_url"),
    aws_access_key_id=os.getenv("s3_access_key"),
    aws_secret_access_key=os.getenv("s3_secret_key")
)


class ProgressPercentage:
    """
    This class used for showing percentage bar when uploading image
    """

    def __init__(self, _file_path: str):
        self._file_path = _file_path
        self._size = float(os.path.getsize(_file_path))
        self._seen_so_far = 0
        self._lock = threading.Lock()

    def __call__(self, bytes_amount):
        """
        To simplify, assume this is hooked up to a single file_path

        :param bytes_amount: uploaded bytes
        """
        with self._lock:
            self._seen_so_far += bytes_amount
            percentage = (self._seen_so_far / self._size) * 100
            sys.stdout.write(
                f"\r{self._file_path} {self._seen_so_far}/{self._size} ({percentage:.2f}%)"
            )
            sys.stdout.flush()

    def __str__(self):
        return f"The file path is {self._file_path}"


def upload_file(file_path: str, bucket: str, object_name: Optional[str] = None, metadata: map = None, chunksize=int):
    """
    Upload a file to an S3 bucket

    :param file_path: File to upload
    :param bucket: Bucket to upload to
    :param object_name: S3 object name. If not specified then file_path is used
    :return: True if file was uploaded, else False
    """
    # If S3 object_name was not specified, use file_path
    if object_name is None:
        object_name = file_path

    # Upload the file
    try:
        # Set the desired multipart threshold value (400 MB)
        config = TransferConfig(multipart_chunksize=chunksize)
        s3_client.upload_file(
            file_path,
            bucket,
            object_name,
            ExtraArgs={'Metadata': metadata},
            Callback=ProgressPercentage(file_path),
            Config=config
        )
    except ClientError as error:
        logging.error(error)
        return False
    return True


KB = 1024
MB = KB * KB

MULTIPART_CHUNKSIZE = 15 * MB
BUCKETNAME = os.getenv("bucketname")

if MULTIPART_CHUNKSIZE < 5 * MB:
    print("MULTIPART_CHUNKSIZE should not be smaller than 5 MB")
    sys.exit()

image_path = os.getenv("image_path")
dir_files = os.path.dirname(image_path)
dir_files = os.path.abspath(dir_files)
CHECKSUM = None
if not os.path.exists(image_path):
    print("image file does not exists")
else:
    DIR = os.getenv("dir") + '/'
    key_name = DIR + os.getenv("object_name")

    md5_hash = hashlib.md5()
    with open(image_path, "rb") as f:
        for byte_block in iter(lambda: f.read(4096), b""):
            md5_hash.update(byte_block)
    CHECKSUM = md5_hash.hexdigest()

    RETRY = 3
    FINISH = False
    while RETRY >= 1:
        print("Image uploading...")
        UPLOAD_SUCCESS = upload_file(image_path, BUCKETNAME, key_name, {}, MULTIPART_CHUNKSIZE)
        if not UPLOAD_SUCCESS:
            RETRY -= 1
            if RETRY == 0:
                break
            print(" Upload is not successful try again...")
        else:
            response = s3_client.head_object(Bucket=BUCKETNAME, Key=key_name)
            etag = response['ETag']
            etag_calc = calculate_multipart_etag(os.getenv("image_path"), MULTIPART_CHUNKSIZE)
            if etag == etag_calc:
                print(" Upload is done successfully")
                FINISH = True
                break
            print(" Checking integrity of the file is not successful try again...")
            RETRY -= 1

    if FINISH:
        tagging = []
        DIR = os.getenv("dir") + '/'
        tagging.append({'Key': 'checksum', 'Value': CHECKSUM})
        response = s3_client.put_object_tagging(
            Bucket=BUCKETNAME,
            Key=key_name,
            Tagging={
                'TagSet': tagging
            },
        )
        print("Checksum of image: " + CHECKSUM)
        print("Checksum tag set on image")
    else:
        print("Upload is not successful")
