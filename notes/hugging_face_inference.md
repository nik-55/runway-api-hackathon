# HuggingFace Inference Router

Base URL: `https://router.huggingface.co/v1`
Auth: `OPENAI_API_KEY` (HF token, starts with `hf_`)

---

## OpenAI SDK Compatibility

| Feature | OpenAI Compatible? | Notes |
|---|---|---|
| Chat / Completions (Kimi K2.6) | ✅ Yes | Use standard OpenAI SDK, just change base URL |
| STT / Whisper | ❌ No | Uses HF-native binary upload format |

---

## 1. Chat Completions — Kimi K2.6 (Thinking Model)

Kimi K2.6 is a **thinking model** — it returns a `reasoning_content` field alongside `content` with its internal chain-of-thought.

### curl

```bash
export OPENAI_API_KEY=hf_your_token

curl --request POST \
  --url https://router.huggingface.co/v1/chat/completions \
  --header "Authorization: Bearer $OPENAI_API_KEY" \
  --header 'Content-Type: application/json' \
  --data '{
    "model": "moonshotai/Kimi-K2.6:fireworks-ai",
    "messages": [
      {"role": "system", "content": "You are a helpful assistant."},
      {"role": "user", "content": "Explain transformers in 3 bullet points."}
    ],
    "max_tokens": 300,
    "temperature": 0.7
  }'
```

### Response shape

```json
{
  "object": "chat.completion",
  "model": "accounts/fireworks/models/kimi-k2p6",
  "choices": [{
    "message": {
      "role": "assistant",
      "content": "Final answer here...",
      "reasoning_content": "Model's internal chain-of-thought thinking..."
    },
    "finish_reason": "stop"
  }],
  "usage": { "prompt_tokens": 38, "completion_tokens": 300, "total_tokens": 338 }
}
```

### Python (OpenAI SDK)

```python
from openai import OpenAI

client = OpenAI(
    api_key="hf_your_token",
    base_url="https://router.huggingface.co/v1"
)

response = client.chat.completions.create(
    model="moonshotai/Kimi-K2.6:fireworks-ai",
    messages=[
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "Explain transformers in 3 bullet points."}
    ],
    max_tokens=300
)

print(response.choices[0].message.content)
# Access reasoning/thinking if needed:
# print(response.choices[0].message.reasoning_content)
```

---

## 2. Speech-to-Text — Whisper Large V3

**Not OpenAI-compatible.** Uses HF-native binary upload. Must convert audio to FLAC first.

### curl

```bash
export OPENAI_API_KEY=hf_your_token

# Convert to FLAC if needed
ffmpeg -i audio.mp3 audio.flac

curl https://router.huggingface.co/hf-inference/models/openai/whisper-large-v3 \
  -X POST \
  -H "Authorization: Bearer $OPENAI_API_KEY" \
  -H 'Content-Type: audio/flac' \
  --data-binary @audio.flac
```

### Response shape

```json
{
  "text": "Full transcription as a single string..."
}
```

### Python (requests — no OpenAI SDK)

```python
import requests

with open("audio.flac", "rb") as f:
    response = requests.post(
        "https://router.huggingface.co/hf-inference/models/openai/whisper-large-v3",
        headers={
            "Authorization": "Bearer hf_your_token",
            "Content-Type": "audio/flac"
        },
        data=f
    )

print(response.json()["text"])
```
