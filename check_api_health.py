import os
from dotenv import load_dotenv
import requests

load_dotenv()

def check_groq():
    key = os.getenv("GROQ_API_KEY")
    if not key:
        print("GROQ_API_KEY missing")
        return
    
    headers = {"Authorization": f"Bearer {key}"}
    try:
        # Simple models list check
        response = requests.get("https://api.groq.com/openai/v1/models", headers=headers, timeout=5)
        if response.status_code == 200:
            print("Groq API: OK")
        else:
            print(f"Groq API: FAILED ({response.status_code}) - {response.text}")
    except Exception as e:
        print(f"Groq API: ERROR - {e}")

def check_gemini():
    key = os.getenv("GOOGLE_API_KEY")
    if not key:
        print("GOOGLE_API_KEY missing")
        return
    
    try:
        # Simple models list check
        response = requests.get(f"https://generativelanguage.googleapis.com/v1beta/models?key={key}", timeout=5)
        if response.status_code == 200:
            print("Gemini API: OK")
        else:
            print(f"Gemini API: FAILED ({response.status_code}) - {response.text}")
    except Exception as e:
        print(f"Gemini API: ERROR - {e}")

if __name__ == "__main__":
    check_groq()
    check_gemini()
