"""Install root-owned as /opt/npd-video-factory/runtime/request.py."""
import sys
sys.path.insert(0, "/opt/npd-video-factory/runtime/source/apps/api")
from app.executor_request import main
raise SystemExit(main())
