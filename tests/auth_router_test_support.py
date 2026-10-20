from importlib import util
from pathlib import Path
import sys


def load_auth_router():
    """Load the auth router file without importing unrelated router packages."""
    module_name = '_dms_auth_router_under_test'
    if module_name in sys.modules:
        return sys.modules[module_name]

    router_file = Path(__file__).resolve().parents[1] / 'routers' / 'auth_router.py'
    spec = util.spec_from_file_location(module_name, router_file)
    if spec is None or spec.loader is None:
        raise ImportError(f'Could not load auth router from {router_file}')
    module = util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module
