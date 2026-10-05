"""Read-only prerequisite check; does not generate models or install anything."""
import importlib,json,sys
from config import HUNYUAN_HOME,HUNYUAN_PYTHON,MODEL_DIR,DATA_DIR
errors=[]
for name in ['torch','hy3dgen','custom_rasterizer','mesh_processor','diffusers','transformers','xatlas','fastapi','multipart']:
 try:importlib.import_module(name)
 except Exception as exc:errors.append(f'{name}: {exc}')
try:
 import torch
 if not torch.cuda.is_available():errors.append('CUDA unavailable')
 else:print('GPU:',torch.cuda.get_device_name(),torch.cuda.get_device_capability())
except Exception:pass
required=['mini-turbo/config.yaml','mini-turbo/model.fp16.safetensors','multiview/config.yaml','multiview/model.fp16.safetensors','multiview/ready.txt','paint/hunyuan3d-delight-v2-0/model_index.json','paint/hunyuan3d-paint-v2-0/model_index.json']
missing=[p for p in required if not (MODEL_DIR/p).is_file()]
print(json.dumps({'home':str(HUNYUAN_HOME),'python':str(HUNYUAN_PYTHON),'models':str(MODEL_DIR),'data':str(DATA_DIR),'missing_models':missing,'errors':errors},indent=2))
sys.exit(1 if errors or missing else 0)
