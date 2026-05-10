# Fireworks AI API Examples

Base URL: `https://api.fireworks.ai/inference/v1`
Auth: Bearer token via `OPENAI_API_KEY` in `.env`

---

## 1. Text Completion (kimi-k2p6)

```bash
export OPENAI_API_KEY=$(grep OPENAI_API_KEY .env | cut -d= -f2)

curl --request POST \
  --url https://api.fireworks.ai/inference/v1/completions \
  --header "Authorization: Bearer $OPENAI_API_KEY" \
  --header 'Content-Type: application/json' \
  --data '{
    "model": "accounts/fireworks/models/kimi-k2p6",
    "prompt": "What is 2 + 2? Answer in one sentence.",
    "max_tokens": 50,
    "temperature": 0.7
  }'
```

**Response:**
```json
{
  "id": "cmpl-...",
  "model": "accounts/fireworks/models/kimi-k2p6",
  "choices": [{ "text": "2 + 2 equals 4.", "finish_reason": "length" }],
  "usage": { "prompt_tokens": 13, "completion_tokens": 50, "total_tokens": 63 }
}
```

---

## 2. Audio Transcription (whisper-v3)

> Note: use short model name `whisper-v3`, not the full path.

```bash
export OPENAI_API_KEY=$(grep OPENAI_API_KEY .env | cut -d= -f2)

curl --request POST \
  --url https://api.fireworks.ai/inference/v1/audio/transcriptions \
  --header "Authorization: Bearer $OPENAI_API_KEY" \
  --form file=@/path/to/audio.mp3 \
  --form model=whisper-v3
```

**Response:**
```json
{
  "text": "Full transcription of the audio as a single string..."
}
```

---

## OpenAI SDK Compatibility

Yes — Fireworks AI is fully OpenAI-compatible. Just point the base URL to Fireworks:

**Python:**
```python
from openai import OpenAI

client = OpenAI(
    api_key="fw_your_key",
    base_url="https://api.fireworks.ai/inference/v1"
)

# Text completion
response = client.completions.create(
    model="accounts/fireworks/models/kimi-k2p6",
    prompt="What is 2 + 2?",
    max_tokens=50
)
print(response.choices[0].text)

# Audio transcription
with open("audio.mp3", "rb") as f:
    transcript = client.audio.transcriptions.create(
        model="whisper-v3",
        file=f
    )
print(transcript.text)
```

**JavaScript/Node:**
```js
import OpenAI from "openai";

const client = new OpenAI({
  apiKey: process.env.OPENAI_API_KEY,
  baseURL: "https://api.fireworks.ai/inference/v1",
});

const response = await client.completions.create({
  model: "accounts/fireworks/models/kimi-k2p6",
  prompt: "What is 2 + 2?",
  max_tokens: 50,
});
console.log(response.choices[0].text);
```
