import asyncio, httpx, os
from dotenv import load_dotenv
load_dotenv()

KEY = os.environ['EURI_API_KEY']
BASE = os.environ.get('EURI_API_BASE_URL', 'https://api.euron.one/api/v1/euri/')

MODELS = [
    # OpenAI — confirmed working prefix
    "gpt-4.1-nano",
    "gpt-4.1-mini",
    "gpt-4.1",
    "gpt-5.4-mini",
    "gpt-4o",
    "gpt-4o-mini",
    # Claude — direct names
    "claude-haiku-4-5",
    "claude-haiku-4-5-20251001",
    "claude-sonnet-4-6",
    "claude-opus-4-7",
    # Gemini
    "gemini-2.5-flash",
    "gemini-2.5-pro",
    "gemini-flash-2.0",
    # DeepSeek (without provider prefix)
    "deepseek-chat",
    "deepseek-r1",
    # Qwen (without prefix)
    "qwen2.5-72b",
]

async def probe(client, model):
    r = await client.post(
        'chat/completions',
        json={'model': model, 'messages': [{'role':'user','content':'hi'}], 'max_tokens': 5},
        timeout=15,
    )
    if r.status_code == 200:
        status = "OK"
    else:
        status = f"HTTP {r.status_code}"
    print(f"{status:12s}  {model}")

async def main():
    async with httpx.AsyncClient(
        base_url=BASE,
        headers={'Authorization': f'Bearer {KEY}', 'Content-Type': 'application/json'},
    ) as c:
        for m in MODELS:
            await probe(c, m)

asyncio.run(main())
