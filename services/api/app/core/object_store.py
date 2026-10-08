"""Server-side object storage. Private objects are served through scoped APIs only."""
from dataclasses import dataclass
from app.core.settings import settings

@dataclass(frozen=True)
class ObjectInfo:
    key: str

class S3Store:
    def __init__(self, config):
        import boto3
        self.bucket = config.object_storage_bucket
        self.client = boto3.client('s3', endpoint_url=config.object_storage_endpoint,
                                   aws_access_key_id=config.object_storage_access_key,
                                   aws_secret_access_key=config.object_storage_secret_key)

    def ensure_container(self):
        from botocore.exceptions import ClientError
        try:
            self.client.head_bucket(Bucket=self.bucket)
        except ClientError as error:
            if error.response['Error']['Code'] not in {'404', 'NoSuchBucket', 'NotFound'}:
                raise
            self.client.create_bucket(Bucket=self.bucket)

    def probe(self):
        # Preserve empty fresh-install readiness without creating an object.
        self.client.list_buckets()

    def put(self, key, body, content_type, metadata):
        self.client.put_object(Bucket=self.bucket, Key=key, Body=body,
                               ContentType=content_type, Metadata=metadata)

    def get(self, key):
        return self.client.get_object(Bucket=self.bucket, Key=key)['Body'].read()

    def objects(self):
        for page in self.client.get_paginator('list_objects_v2').paginate(Bucket=self.bucket):
            for item in page.get('Contents', []):
                yield ObjectInfo(item['Key'])

class AzureStore:
    def __init__(self, config):
        from azure.storage.blob import BlobServiceClient
        if config.azure_storage_connection_string:
            service = BlobServiceClient.from_connection_string(config.azure_storage_connection_string)
        elif config.azure_storage_account_url and config.azure_storage_account_key:
            service = BlobServiceClient(config.azure_storage_account_url,
                                        credential=config.azure_storage_account_key)
        else:
            raise ValueError('Azure storage connection string or account URL/key required')
        self.bucket = config.azure_storage_container
        self.prefix = config.azure_storage_prefix.strip('/') + '/'
        if self.prefix == '/':
            raise ValueError('Non-empty Azure application prefix required')
        self.create_container = config.azure_storage_create_container
        self.container = service.get_container_client(self.bucket)

    def ensure_container(self):
        from azure.core.exceptions import ResourceExistsError
        if not self.create_container:
            self.probe()
            return
        try:
            # No public access; evidence/download URLs stay authenticated in GreenOps.
            self.container.create_container(public_access=None)
        except ResourceExistsError:
            pass
        self.probe()

    def probe(self):
        properties = self.container.get_container_properties()
        if properties.get('public_access'):
            raise ValueError('Azure GreenOps container must be private')

    def put(self, key, body, content_type, metadata):
        from azure.storage.blob import ContentSettings
        self.container.upload_blob(name=self.prefix + key, data=body, overwrite=True, metadata=metadata,
                                   content_settings=ContentSettings(content_type=content_type))

    def get(self, key):
        return self.container.download_blob(self.prefix + key).readall()

    def objects(self):
        for blob in self.container.list_blobs(name_starts_with=self.prefix):
            yield ObjectInfo(blob.name[len(self.prefix):])

def object_store(config=None):
    config = config or settings()
    return AzureStore(config) if config.object_storage_provider == 'azure' else S3Store(config)
