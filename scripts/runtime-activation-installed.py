"""Root-owned fixed launcher for runtime LOGIN lifecycle."""
import sys
sys.path.insert(0, "/opt/npd-video-factory/runtime/source/apps/api")
from app.runtime_activation_host import main
raise SystemExit(main())
