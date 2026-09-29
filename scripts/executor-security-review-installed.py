"""Install root-owned as /opt/npd-video-factory/runtime/security-review.py."""
import sys
sys.path.insert(0, "/opt/npd-video-factory/runtime/source/apps/api")
from app.executor_security import main
raise SystemExit(main())
