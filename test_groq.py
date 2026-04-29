"""Test directo de Groq API."""
import requests
import json
from config import GROQ_API_KEY

print(f"Key: {GROQ_API_KEY[:15]}...")

# Test REST API
url = "https://api.groq.com/openai/v1/chat/completions"
headers = {
    "Authorization": f"Bearer {GROQ_API_KEY}",
    "Content-Type": "application/json",
}
payload = {
    "model": "llama-3.3-70b-versatile",
    "messages": [
        {"role": "user", "content": "Di 'hola' en una palabra"}
    ],
    "temperature": 0.3,
    "max_tokens": 50,
}

try:
    r = requests.post(url, headers=headers, json=payload, timeout=20)
    print(f"Status: {r.status_code}")
    print(f"Response: {r.text[:500]}")
except Exception as e:
    print(f"Error: {e}")
