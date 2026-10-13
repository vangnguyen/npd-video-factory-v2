"""Optional Hub boundary initialization; invalid local custody disables only Hub."""
from .bridge_auth import ServiceAuthVerifier,SigningKeyring
from .bridge_repository import BridgeRepository
from .bridge_service import AgentHubBridgeService
from .service_api_repository import ServiceOperationRepository

def configure(app,*,settings,factory,queue,platform,publishing,analytics,default_workspace_id):
    app.state.service_api_repository=ServiceOperationRepository(factory)
    app.state.service_api_enabled=False;app.state.bridge_auth_verifier=None;app.state.agent_hub_bridge_service=None
    app.state.service_api_configuration_state='disabled'
    if not settings.agent_hub_bridge_enabled:return
    try:
        verifier=ServiceAuthVerifier.from_file(settings.agent_hub_service_keys_file,queue,
            max_clock_skew_seconds=settings.service_auth_max_clock_skew_seconds,replay_ttl_seconds=settings.service_auth_replay_ttl_seconds)
        if settings.agent_hub_webhook_mode!='disabled':SigningKeyring.from_file(settings.agent_hub_webhook_signing_keys_file)
        service=AgentHubBridgeService(repository=BridgeRepository(factory),platform_repository=platform,
            publishing_repository=publishing,analytics_repository=analytics,queue=queue,default_workspace_id=default_workspace_id,
            webhook_destination_ref=settings.agent_hub_webhook_destination_ref,webhook_provider_mode=settings.agent_hub_webhook_mode,
            webhook_max_attempts=settings.agent_hub_webhook_max_attempts,production_deployed=settings.app_env.lower()=='production')
    except (OSError,ValueError,TypeError,KeyError):
        app.state.service_api_configuration_state='not_configured';return
    app.state.bridge_auth_verifier=verifier;app.state.agent_hub_bridge_service=service
    app.state.service_api_enabled=True;app.state.service_api_configuration_state='configured'
