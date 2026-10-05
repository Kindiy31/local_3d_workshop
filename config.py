"""Portable configuration. Values are Linux paths when running in WSL."""
import os
from pathlib import Path
ROOT = Path(__file__).resolve().parent
STATE = Path(os.environ.get('WORKSHOP_STATE', str(Path.home()/'.local/share/local-3d-workshop'))).expanduser().resolve()
DATA_DIR = Path(os.environ.get('WORKSHOP_DATA', str(ROOT/'runtime'))).expanduser().resolve()
HUNYUAN_HOME = Path(os.environ.get('HUNYUAN_HOME', str(STATE/'Hunyuan3D-2'))).expanduser().resolve()
HUNYUAN_PYTHON = Path(os.environ.get('HUNYUAN_PYTHON', str(HUNYUAN_HOME/'.venv/bin/python'))).expanduser().resolve()
MODEL_DIR = Path(os.environ.get('HUNYUAN_MODELS', str(STATE/'models'))).expanduser().resolve()
