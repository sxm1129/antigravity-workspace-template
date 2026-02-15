
import os
import time
import requests
import base64
import random
from datetime import datetime

# FLUX API Configuration (matching backend/routes/research.py defaults)
FLUX_API_BASE = os.getenv("FLUX_API_BASE", "http://47.92.252.119:8080/api/v1")
FLUX_API_KEY = os.getenv("FLUX_API_KEY", "fx-commonwtpKmZL6XPKFrqrnvDRszLxtjM0w62DHULzGfwqL2K")
FLUX_API_TIMEOUT = 120

def generate_test_image(prompt, orientation, output_prefix):
    url = f"{FLUX_API_BASE}/images/generations"
    headers = {
        "Authorization": f"Bearer {FLUX_API_KEY}",
        "Content-Type": "application/json"
    }

    # Configuration logic from research.py
    if orientation == "vertical":
        size = "1080x1920"
        model = "FLUX.1-schnell"  # Updated logic
    else:
        size = "1920x1080"
        model = "FLUX.1-schnell"

    seed = random.randint(1, 2**32 - 1)
    
    payload = {
        "model": model,
        "prompt": prompt,
        "n": 1,
        "size": size,
        "seed": seed
    }

    print(f"\n🚀 Testing {orientation} ({size})...")
    print(f"Model: {model}")
    print(f"Prompt: {prompt[:50]}...")

    try:
        start_time = time.time()
        response = requests.post(url, headers=headers, json=payload, timeout=FLUX_API_TIMEOUT)
        elapsed = time.time() - start_time

        if response.status_code == 200:
            result = response.json()
            if "data" in result and len(result["data"]) > 0:
                item = result["data"][0]
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = f"{output_prefix}_{orientation}_{timestamp}.png"
                
                # Handle B64 JSON or URL
                if "b64_json" in item:
                    image_data = base64.b64decode(item["b64_json"])
                    with open(filename, "wb") as f:
                        f.write(image_data)
                    print(f"✅ Success! Saved to: {filename}")
                    print(f"⏱️ Generation time: {elapsed:.2f}s")
                    print(f"📦 Size: {len(image_data)/1024:.2f} KB")
                    return True
                elif "url" in item:
                    img_resp = requests.get(item['url'], timeout=30)
                    if img_resp.status_code == 200:
                        with open(filename, "wb") as f:
                            f.write(img_resp.content)
                        print(f"✅ Success! Saved to: {filename}")
                        print(f"⏱️ Generation time: {elapsed:.2f}s")
                        print(f"📦 Size: {len(img_resp.content)/1024:.2f} KB")
                        return True
            
            print("❌ Failed: Valid data not found in response")
            print(result)
        else:
            print(f"❌ Failed: HTTP {response.status_code}")
            print(response.text)
            
    except Exception as e:
        print(f"❌ Error: {str(e)}")
    
    return False

if __name__ == "__main__":
    print(f"Testing FLUX generation in current directory: {os.getcwd()}")
    
    # Test 1: Horizontal
    generate_test_image(
        "A futuristic city skyline at sunset, cyberpunk style, high details", 
        "horizontal", 
        "test_flux"
    )
    
    # Test 2: Vertical
    generate_test_image(
        "A tall magical tower reaching into the clouds, fantasy art, high details", 
        "vertical", 
        "test_flux"
    )
