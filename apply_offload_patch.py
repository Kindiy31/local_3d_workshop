"""Idempotent CPU-offload compatibility patch for the pinned upstream revision."""
from config import HUNYUAN_HOME
p=HUNYUAN_HOME/'hy3dgen/texgen/hunyuanpaint/pipeline.py'
s=p.read_text();marker='        # For classifier free guidance, we need to do two forward passes.'
patch='        prompt_embeds = prompt_embeds.to(device)\n        if negative_prompt_embeds is not None:\n            negative_prompt_embeds = negative_prompt_embeds.to(device)\n\n'
if patch in s or 'prompt_embeds = prompt_embeds.to(device)' in s[s.index(marker)-400:s.index(marker)]:print('Offload patch already present')
else:
 if s.count(marker)!=1:raise RuntimeError('Unexpected upstream version; inspect manually')
 backup=p.with_suffix('.py.before-workshop');backup.write_text(s)
 p.write_text(s.replace(marker,patch+marker));print('Patched',p)
