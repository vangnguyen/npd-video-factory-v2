"""Independent local acceptance receiver; public schemas + external jsonschema only.

Not an Agent Hub implementation or deployment tool. Binds loopback, accepts only
synthetic qualified events, and keeps its own SQLite idempotency/receipt ledger.
"""
import argparse,hashlib,hmac,json,os,socket,sqlite3,threading,time
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
from jsonschema import Draft202012Validator,FormatChecker

KEYS={'fixture-v1':b'explicit-meta-webhook-fixture-key-only-001',
      'fixture-v2':b'explicit-meta-webhook-fixture-key-only-002'}
CONTROL='explicit-local-receiver-fixture-control-only'


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--root',required=True);parser.add_argument('--schema',required=True)
    parser.add_argument('--workspace',required=True)
    parser.add_argument('--scenario',choices=('normal','lost_response','rate_limit'),default='normal')
    parser.add_argument('--resume-fixture',action='store_true')
    parser.add_argument('--port',type=int,default=0)
    args=parser.parse_args();root=Path(args.root).resolve()
    assert 0<=args.port<65536
    schema=json.loads(Path(args.schema).read_bytes())
    assert schema['$id'].endswith('/agent-hub-qualified-feedback.v1.schema.json')
    validator=Draft202012Validator(schema,format_checker=FormatChecker())
    marker={'schema_version':'meta-webhook-fixture-receiver-v1','workspace':args.workspace,'scenario':args.scenario,
        'public_contract_sha256':hashlib.sha256(Path(args.schema).read_bytes()).hexdigest()}
    if args.resume_fixture:
        assert json.loads((root/'fixture.json').read_bytes())==marker
        assert (root/'receiver.sqlite3').is_file()
    else:
        root.mkdir(parents=True,exist_ok=False)
        (root/'fixture.json').write_text(json.dumps(marker),encoding='utf-8')
    db=root/'receiver.sqlite3';lock=threading.Lock()
    def connection():return sqlite3.connect(db,timeout=10)
    with connection() as con:
        if args.resume_fixture:
            assert con.execute('PRAGMA quick_check').fetchone()[0]=='ok'
            for row in con.execute('SELECT event_id,body_sha256,body FROM events'):
                value=json.loads(row[2]);validator.validate(value)
                assert row[0]==value['event_id'] and row[1]==hashlib.sha256(row[2]).hexdigest()
                assert value['payload']['workspace_id']==args.workspace and value['payload']['mock'] is True
        else:con.executescript('''CREATE TABLE events(event_id TEXT PRIMARY KEY,body_sha256 TEXT NOT NULL,body BLOB NOT NULL);
            CREATE TABLE requests(sequence INTEGER PRIMARY KEY AUTOINCREMENT,event_id TEXT,body_sha256 TEXT,
                key_id TEXT,status INTEGER NOT NULL,duplicate INTEGER NOT NULL,accepted INTEGER NOT NULL);''')
    class Handler(BaseHTTPRequestHandler):
        def setup(self):
            super().setup();self.connection.settimeout(10)
        def log_message(self,*_):pass
        def reply(self,status,value=None,retry=None):
            data=b'' if value is None else json.dumps(value,sort_keys=True).encode()
            self.send_response(status);self.send_header('Content-Type','application/json')
            self.send_header('Content-Length',str(len(data)));self.send_header('Cache-Control','no-store')
            if retry is not None:self.send_header('Retry-After',str(retry))
            self.end_headers()
            if data:self.wfile.write(data)
        def do_GET(self):
            if self.path!='/__fixture__/state':return self.reply(404)
            with lock,connection() as con:
                events=[{'event_id':r[0],'body_sha256':r[1],'envelope':json.loads(r[2])} for r in con.execute('SELECT * FROM events ORDER BY event_id')]
                rows=[dict(zip(('sequence','event_id','body_sha256','key_id','status','duplicate','accepted'),r)) for r in con.execute('SELECT * FROM requests ORDER BY sequence')]
            return self.reply(200,{'fixture':True,'real_Agent_Hub':False,'events':events,'requests':rows,'pid':os.getpid()})
        def do_POST(self):
            if self.path=='/__fixture__/stop':
                if self.headers.get('X-Fixture-Control')!=CONTROL:return self.reply(403)
                self.reply(204);threading.Thread(target=self.server.shutdown,daemon=True).start();return
            if self.path!='/agent-hub/events/v1':return self.reply(404)
            try:
                size=int(self.headers.get('Content-Length',''));assert 0<size<=32768
                assert self.headers.get('Content-Type')=='application/json'
                body=self.rfile.read(size);assert len(body)==size
                sha=hashlib.sha256(body).hexdigest();identity=self.headers['X-NPD-Event-Id'];key_id=self.headers['X-NPD-Key-Id']
                timestamp=int(self.headers['X-NPD-Timestamp']);assert abs(time.time()-timestamp)<=300
                assert self.headers['X-NPD-Contract-Version']=='agent-hub-bridge.v1'
                assert self.headers['X-NPD-Content-SHA256']==sha and self.headers['Idempotency-Key']==identity
                canonical='\n'.join(('POST','/agent-hub/events/v1',str(timestamp),identity,sha)).encode()
                signature=hmac.new(KEYS[key_id],canonical,hashlib.sha256).hexdigest()
                assert hmac.compare_digest(signature,self.headers['X-NPD-Signature'])
                def pairs(items):
                    result={}
                    for k,v in items:
                        if k in result:raise ValueError('duplicate key')
                        result[k]=v
                    return result
                value=json.loads(body,object_pairs_hook=pairs);validator.validate(value)
                assert value['event_id']==identity and value['payload']['workspace_id']==args.workspace
                p=value['payload'];assert p['mock'] is True and p['real_audience_observation'] is False and p['provider_calls']==0
            except Exception:return self.reply(401)
            with lock,connection() as con:
                count=con.execute('SELECT count(*) FROM requests').fetchone()[0]
                if args.scenario=='rate_limit' and count==0:
                    con.execute('INSERT INTO requests(event_id,body_sha256,key_id,status,duplicate,accepted) VALUES(?,?,?,?,0,0)',(identity,sha,key_id,429))
                    con.commit();return self.reply(429,retry=40)
                old=con.execute('SELECT body_sha256 FROM events WHERE event_id=?',(identity,)).fetchone()
                status=409 if old and old[0]!=sha else 204;duplicate=old is not None;accepted=status==204
                if accepted and not duplicate:con.execute('INSERT INTO events VALUES(?,?,?)',(identity,sha,body))
                lost=args.scenario=='lost_response' and count==0 and accepted
                con.execute('INSERT INTO requests(event_id,body_sha256,key_id,status,duplicate,accepted) VALUES(?,?,?,?,?,?)',
                    (identity,sha,key_id,0 if lost else status,int(duplicate),int(accepted)))
                con.commit()
            if lost:
                self.connection.shutdown(socket.SHUT_RDWR);self.connection.close();return
            return self.reply(status)
    server=ThreadingHTTPServer(('127.0.0.1',args.port),Handler);server.daemon_threads=True
    ready={'fixture':True,'port':server.server_port,'pid':os.getpid(),'workspace':args.workspace,'scenario':args.scenario}
    (root/'ready.json').write_text(json.dumps(ready),encoding='utf-8')
    print(json.dumps(ready),flush=True)
    try:server.serve_forever(poll_interval=.1)
    finally:server.server_close()


if __name__=='__main__':main()
