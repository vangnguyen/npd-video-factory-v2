"""Explicit in-memory S3 protocol fixture; no storage provider/network acceptance."""
import hashlib,io
from urllib.parse import urlencode
from app.publishing_media_delivery import MediaDeliveryError, ProtocolFixtureDeliveryWire

class FixtureStore:
    def __init__(self,profile,clock):
        self.profile,self.clock=profile,clock;self.objects={};self.calls=[];self.puts=0;self.lose_reply=False;self.after_put=None;self.bodies=[];self.url_override=None
        self.wire=ProtocolFixtureDeliveryWire(profile,self.call,self.sign)
    def call(self,operation,args):
        self.calls.append((operation,args['Key']))
        if operation=='put_object':
            if args['Key'] in self.objects:raise MediaDeliveryError('MEDIA_DELIVERY_OBJECT_ALREADY_EXISTS')
            assert args['IfNoneMatch']=='*';data=args['Body'].read();self.puts+=1
            self.objects[args['Key']]={'data':data,'ContentLength':len(data),'ContentType':args['ContentType'],'Metadata':dict(args['Metadata']),
                'ETag':'"'+hashlib.md5(data).hexdigest()+'"','VersionId':'fixture-version-1'}
            if self.after_put:self.after_put()
            if self.lose_reply:raise MediaDeliveryError('MEDIA_DELIVERY_OPERATION_UNCONFIRMED',uncertain=True)
            return {'ETag':self.objects[args['Key']]['ETag'],'VersionId':'fixture-version-1'}
        obj=self.objects.get(args['Key'])
        if obj is None:raise MediaDeliveryError('MEDIA_DELIVERY_OBJECT_ABSENT')
        response={k:v for k,v in obj.items() if k!='data'}
        if operation=='get_object':
            assert args.get('VersionId')==obj['VersionId'] or args.get('IfMatch')==obj['ETag']
            body=io.BytesIO(obj['data']);self.bodies.append(body);response['Body']=body
        return response
    def sign(self,key,ttl,version_id):
        if self.url_override:return self.url_override
        return self.profile.public_prefix+key+'?'+urlencode({'versionId':version_id,'X-Amz-Expires':ttl,'X-Amz-Date':self.clock().strftime('%Y%m%dT%H%M%SZ'),
            'X-Amz-Algorithm':'AWS4-HMAC-SHA256','X-Amz-SignedHeaders':'host',
            'X-Amz-Credential':'EXPLICIT-FIXTURE-ACCESS/'+self.clock().strftime('%Y%m%d')+'/'+self.profile.region+'/s3/aws4_request','X-Amz-Signature':'a'*64})
