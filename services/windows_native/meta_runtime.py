"""Validate opt-in Meta/media runtime before sockets; injectable wires are mocks."""
from pathlib import Path
from .contracts import WorkflowError


def validate(root,access,*,meta_registry,meta_enabled,meta_factories,account_registry,account_factories,account_reads,
             media_registry,media_enabled,media_factory,session_directory):
    from .access import NativeAccess
    from .meta_distribution import NativeMetaPublishingFactory
    from .publishing_media_delivery import NativeMediaDeliveryFactory
    from app.publishing_media_delivery import ProtocolFixtureDeliveryWire
    import httpx
    if type(meta_enabled) is not bool or type(media_enabled) is not bool:raise WorkflowError('NATIVE_META_MEDIA_RUNTIME_INVALID',400)
    if meta_registry is not None and meta_factories is not None or media_registry is not None and media_factory is not None:
        raise WorkflowError('NATIVE_META_MEDIA_RUNTIME_CONFIGURATION_CONFLICT',400)
    has_meta=meta_registry is not None or meta_factories is not None;has_media=media_registry is not None or media_factory is not None
    if (has_meta or has_media or meta_enabled or media_enabled) and not isinstance(access,NativeAccess):
        raise WorkflowError('NATIVE_META_MEDIA_RUNTIME_HUMAN_AUTH_REQUIRED',400)
    if meta_enabled and (not has_meta or not account_reads or session_directory is None):
        raise WorkflowError('NATIVE_META_PROTECTED_REGISTRY_READS_AND_VAULT_REQUIRED',400)
    if has_meta and account_registry is None and account_factories is None:raise WorkflowError('NATIVE_META_ACCOUNT_REGISTRY_REQUIRED',400)
    if media_enabled and not has_media:raise WorkflowError('NATIVE_MEDIA_PROTECTED_REGISTRY_REQUIRED',400)
    if media_factory is not None:
        if (type(media_factory) is not NativeMediaDeliveryFactory or type(media_factory.wire) is not ProtocolFixtureDeliveryWire
            or media_factory.wire.mock is not True or media_factory.wire.network_enabled is not False
            or media_factory.root!=Path(root).absolute() or media_factory.workspace!=access.workspace_id):
            raise WorkflowError('NATIVE_MEDIA_RUNTIME_MOCK_INJECTION_REQUIRED',400)
        media_factory.check()
    if meta_factories is not None:
        if (type(meta_factories) is not dict or len(meta_factories)>50 or type(account_factories) is not dict
            or any(type(f) is not NativeMetaPublishingFactory or key!=f.profile.target.profile_id
                or f.connection is not account_factories.get(f.connection.account.account_ref)
                or f.root!=Path(root).absolute() or f.workspace!=access.workspace_id
                or type(f.client.transport) is not httpx.MockTransport or f.client.network_enabled is not False
                for key,f in meta_factories.items())):raise WorkflowError('NATIVE_META_DISTRIBUTION_MOCK_INJECTION_REQUIRED',400)
        for f in meta_factories.values():f.check()
    return has_meta,has_media


def media(root,workspace,*,registry,factory,enabled):
    from .publishing_media_registry import load
    from .publishing_media_delivery import NativeMediaDeliveryFactory
    if registry is not None:return load(registry,root,workspace,owner_enabled=enabled)
    if factory is None:return None
    return NativeMediaDeliveryFactory(factory.profile,root,workspace,enabled=enabled and factory.enabled,directory=factory.directory,
        credential_file=factory.credential_file,credential_expires_at=factory.expires_at,estimated_operation_cost_vnd=factory.estimate,
        wire=factory.wire,clock=factory.clock,registry_file=factory.registry_file,registry_sha256=factory.registry_sha256)


def distribution(root,workspace,accounts,*,registry,factories,enabled,media_factory):
    from .meta_distribution import load_runtime,NativeMetaPublishingFactory
    if registry is not None:values=load_runtime(registry,root,workspace,accounts,owner_enabled=enabled)
    else:
        values={}
        for key,f in (factories or {}).items():
            connection=accounts.get(f.connection.account.account_ref)
            if connection is None:raise WorkflowError('NATIVE_META_DISTRIBUTION_ACCOUNT_BINDING_CHANGED')
            values[key]=NativeMetaPublishingFactory(connection,gates=f.gates,options=f.options,owner_enabled=enabled,
                registry_file=f.registry_file,registry_sha256=f.registry_sha256,execution=f.execution)
    if enabled:
        for f in values.values():
            if not f.execution_supported:continue
            if media_factory is None or not media_factory.enabled:raise WorkflowError('NATIVE_META_MEDIA_PROTECTED_RUNTIME_REQUIRED',400)
            if f.execution.media_configuration_sha256!=media_factory.sha256:raise WorkflowError('NATIVE_META_MEDIA_CONFIGURATION_BINDING_CHANGED',400)
            if f.public()['mock'] is not media_factory.wire.mock:raise WorkflowError('NATIVE_META_MEDIA_RUNTIME_MODE_CHANGED',400)
    return values
