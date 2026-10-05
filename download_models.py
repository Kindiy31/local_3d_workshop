"""Download model files to configurable local storage; reuse HF cache."""
import argparse,shutil,time
from pathlib import Path
from huggingface_hub import hf_hub_download,snapshot_download
from config import MODEL_DIR
parser=argparse.ArgumentParser();parser.add_argument('--models',nargs='+',choices=['mini','multiview','paint'],default=['mini','multiview','paint']);args=parser.parse_args()
def retry(call):
 for i in range(12):
  try:return call()
  except Exception as exc:
   print(f'Download failed ({i+1}/12): {exc}. Cache retained.',flush=True)
   if i==11:raise
   time.sleep(30)
for kind in args.models:
 if kind=='paint':
  prefixes=['hunyuan3d-delight-v2-0','hunyuan3d-paint-v2-0']
  cached=Path(retry(lambda:snapshot_download('tencent/Hunyuan3D-2',allow_patterns=[p+'/**' for p in prefixes])))
  for p in prefixes:shutil.copytree(cached/p,MODEL_DIR/'paint'/p,dirs_exist_ok=True)
  continue
 repo,sub,dest=('tencent/Hunyuan3D-2mini','hunyuan3d-dit-v2-mini-turbo','mini-turbo') if kind=='mini' else ('tencent/Hunyuan3D-2mv','hunyuan3d-dit-v2-mv','multiview')
 target=MODEL_DIR/dest;target.mkdir(parents=True,exist_ok=True)
 for name in ['config.yaml','model.fp16.safetensors']:
  print(kind,name,flush=True)
  cached=retry(lambda: hf_hub_download(repo,filename=sub+'/'+name));shutil.copy2(cached,target/name)
 (target/'ready.txt').write_text(repo+'/'+sub+'\n')
print('Models ready:',MODEL_DIR)
