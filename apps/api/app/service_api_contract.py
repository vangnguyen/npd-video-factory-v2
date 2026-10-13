"""Provider/database-free service grants; never confer a human role."""
import re
from types import MappingProxyType

VERSION='video-factory-service.v1'
CAPABILITIES=frozenset({'project.create','project.read','project.write','content.generate','upload.write','upload.read',
 'analysis.create','analysis.read','timeline.read','timeline.write','preview.create','render.create','render.read',
 'approval.submit','publication.create','publication.read','analytics.read','trend.read','trend.refresh','ideas.generate'})

def grants(value):
    if value is None:return MappingProxyType({})
    if not isinstance(value,dict) or len(value)>100:raise ValueError('SERVICE_API_GRANTS_INVALID')
    result={}
    for workspace,actions in value.items():
        if (type(workspace) is not str or not re.fullmatch(r'wsp_[A-Za-z0-9_-]{4,60}',workspace)
            or not isinstance(actions,(list,tuple)) or not actions or len(actions)>len(CAPABILITIES)
            or any(type(a) is not str or a not in CAPABILITIES for a in actions) or len(set(actions))!=len(actions)):
            raise ValueError('SERVICE_API_GRANTS_INVALID')
        result[workspace]=tuple(actions)
    return MappingProxyType(result)
