"""Bounded signed webhook transport. Disabled is the default; no browser use."""
from dataclasses import dataclass
import http.client
import ipaddress
import re
import socket
import ssl
from urllib.parse import urlsplit
from .contracts import WorkflowError


@dataclass(frozen=True)
class BridgeResponse:
    status: int
    retry_after: int | None = None


class HTTPSWebhookTransport:
    external_call = True
    mode = 'http'

    def __init__(self, endpoint, *, approved_host):
        parsed=urlsplit(endpoint)
        if (parsed.scheme!='https' or parsed.hostname!=approved_host or parsed.port not in (None,443)
            or parsed.username or parsed.password or parsed.query or parsed.fragment
            or parsed.path!='/agent-hub/events/v1' or not re.fullmatch(r'[a-z0-9.-]{3,253}',approved_host)
            or '..' in approved_host):
            raise WorkflowError('NATIVE_BRIDGE_DESTINATION_INVALID',400)
        self.endpoint,self.host=endpoint,approved_host

    def send(self, body, headers):
        # Connect to the validated IP, while retaining TLS SNI and certificate
        # verification for the approved hostname. No redirects or DNS rebind.
        addresses=socket.getaddrinfo(self.host,443,type=socket.SOCK_STREAM)
        if not addresses or any(not ipaddress.ip_address(row[4][0]).is_global for row in addresses):
            raise WorkflowError('NATIVE_BRIDGE_DESTINATION_NOT_PUBLIC',400)
        address=addresses[0][4][0]
        connection=http.client.HTTPSConnection(self.host,443,timeout=10,context=ssl.create_default_context())
        connection._create_connection=lambda _address,timeout,source_address=None: socket.create_connection((address,443),timeout,source_address)
        try:
            connection.request('POST','/agent-hub/events/v1',body=body,headers=headers)
            response=connection.getresponse()
            # Response content is never retained: it could contain secrets or
            # unrelated private content. Its size and network time are bounded.
            if len(response.read(65537))>65536:raise WorkflowError('NATIVE_BRIDGE_RESPONSE_TOO_LARGE')
            retry=response.getheader('Retry-After','')
            return BridgeResponse(response.status,min(3600,int(retry)) if retry.isdigit() else None)
        finally:connection.close()


class FixtureWebhookTransport:
    """Explicit in-process receiver: a delivered fixture is not a Hub receipt."""
    external_call = False
    mode = 'fixture'

    def __init__(self, receiver):self.receiver=receiver

    def send(self,body,headers):return self.receiver(body,headers)
