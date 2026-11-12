"""One tiny Claude call to check the key, model name and endpoint (costs well under $0.001).

  python scripts/check_key.py                       # reads key/apikey.txt
  HDMG_WORKSPACE_ID=wrkspc_... python scripts/check_key.py   # if the key is org-scoped
"""
import os, sys
from openai import OpenAI

root = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
key = os.environ.get("HDMG_API_KEY") or open(os.path.join(root, "key", "apikey.txt")).read().strip()
model = os.environ.get("HDMG_MODEL", "claude-haiku-5-5")
ws = os.environ.get("HDMG_WORKSPACE_ID")
client = OpenAI(api_key=key, base_url="https://api.anthropic.com/v1/",
                default_headers={"anthropic-workspace-id": ws} if ws else None)
try:
    r = client.chat.completions.create(model=model, max_tokens=20,
                                       messages=[{"role": "user", "content": "Reply with the word ok."}])
except Exception as e:
    msg = str(e)
    print("FAILED:", msg[:400])
    if "workspace" in msg.lower():
        print("-> The key is not scoped to a workspace. Either recreate it with Scope = your project"
              " workspace, or set HDMG_WORKSPACE_ID to that workspace's id (Console > Workspaces).")
    elif "401" in msg or "authentication" in msg.lower():
        print("-> Key rejected. Check key/apikey.txt holds exactly the key, nothing else.")
    elif "model" in msg.lower():
        print(f"-> Model name '{model}' not accepted. Set HDMG_MODEL.")
    sys.exit(1)
u = r.usage
print(f"OK  model={r.model}  reply={r.choices[0].message.content!r}  "
      f"tokens in/out={u.prompt_tokens}/{u.completion_tokens}  "
      f"cost=${(u.prompt_tokens * 0.10 + u.completion_tokens * 0.50) / 1e6:.6f} (Haiku 5.5 prices)")
