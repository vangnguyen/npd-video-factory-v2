"""Install root-owned as /opt/npd-video-factory/runtime/qualify.py."""
import sys
sys.path.insert(0, "/opt/npd-video-factory/runtime/source/apps/api")
from app.executor_qualification import main
raise SystemExit(main())
