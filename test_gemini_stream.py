import json
import os
import google.generativeai as genai
from dotenv import load_dotenv

load_dotenv()
KEY = os.getenv("GEMINI_API_KEY")
genai.configure(api_key=KEY)

def generate_stream():
    model = genai.GenerativeModel('gemini-2.5-flash')
    response = model.generate_content("Say hello in stream format.", stream=True)
    for chunk in response:
        print("YIELDING CHUNK:", chunk.text)
        yield chunk.text

if __name__ == "__main__":
    print("Testing RAW generation...")
    generator = generate_stream()
    for text in generator:
        print(text)
    
