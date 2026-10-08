import hashlib
import boto3
from botocore.exceptions import ClientError
from app.core.settings import settings
from app.core.records import insert,get,serialize

MAX_FILE_BYTES=10*1024*1024
ALLOWED_TYPES={'text/plain','text/csv','application/pdf','image/png','image/jpeg','text/html'}
def client():
    s=settings()
    return boto3.client('s3',endpoint_url=s.object_storage_endpoint,aws_access_key_id=s.object_storage_access_key,
                        aws_secret_access_key=s.object_storage_secret_key)

def store(db,scope,name,body,content_type,category='evidence'):
    if len(body)>MAX_FILE_BYTES or content_type not in ALLOWED_TYPES:raise ValueError('File size/type not allowed')
    if category=='evidence' and content_type=='text/html':raise ValueError('HTML evidence uploads are not allowed')
    if content_type=='application/pdf' and not body.startswith(b'%PDF-'):raise ValueError('Invalid PDF signature')
    if content_type=='image/png' and not body.startswith(b'\x89PNG\r\n\x1a\n'):raise ValueError('Invalid PNG signature')
    if content_type=='image/jpeg' and not body.startswith(b'\xff\xd8'):raise ValueError('Invalid JPEG signature')
    s=settings();s3=client()
    try:s3.head_bucket(Bucket=s.object_storage_bucket)
    except ClientError as e:
        if e.response['Error']['Code'] not in {'404','NoSuchBucket','NotFound'}:raise
        s3.create_bucket(Bucket=s.object_storage_bucket)
    sha=hashlib.sha256(body).hexdigest();key=f'{scope.principal.organization_id}/{scope.world.facility_id}/{scope.world.id}/{category}/{sha}'
    s3.put_object(Bucket=s.object_storage_bucket,Key=key,Body=body,ContentType=content_type,
                  Metadata={'sha256':sha})
    row=insert(db,scope,'stored_files',{'key':key,'sha256':sha,'bytes':len(body),'content_type':content_type,'filename':name},name=name,
                 category=category,owner_id=scope.principal.user_id,zone_code=scope.zone_codes[0] if scope.zone_codes else None)
    return serialize(row)

def read(db,scope,file_id):
    row=get(db,scope,'stored_files',file_id);s=settings()
    body=client().get_object(Bucket=s.object_storage_bucket,Key=row.data['key'])['Body'].read()
    if hashlib.sha256(body).hexdigest()!=row.data['sha256']:raise ValueError('Stored artifact checksum mismatch')
    return row,body
