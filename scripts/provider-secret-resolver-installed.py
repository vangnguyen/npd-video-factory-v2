"""Root-owned fixed launcher for the privileged systemd resolver."""
import sys
sys.path.insert(0, "/opt/npd-video-factory/runtime/source/apps/api")
from app.provider_secret_resolver import service_main
raise SystemExit(service_main())
