"""
Environment Setup Verification Script
Checks if all required API keys are configured and tests connectivity.
"""

import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# Load .env file
env_path = Path(__file__).parent / '.env'
if env_path.exists():
    load_dotenv(env_path)
    print(f"✅ Loaded .env from: {env_path}\n")
else:
    print(f"❌ .env file not found at: {env_path}")
    print(f"   Please create backend/.env with your API keys\n")
    sys.exit(1)

# Color codes
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
RESET = "\033[0m"
BOLD = "\033[1m"

def check_var(name, required=True):
    """Check if environment variable is set."""
    value = os.environ.get(name, '').strip()
    if value and not value.endswith('_here') and 'your_' not in value.lower():
        print(f"  {GREEN}✅{RESET} {name}: {value[:20]}..." if len(value) > 20 else f"  {GREEN}✅{RESET} {name}: {value}")
        return True
    elif required:
        print(f"  {RED}❌{RESET} {name}: {YELLOW}NOT SET{RESET} (required)")
        return False
    else:
        print(f"  {YELLOW}⚠️ {RESET} {name}: {YELLOW}NOT SET{RESET} (optional)")
        return True

print(f"{BOLD}🔍 Environment Setup Verification{RESET}")
print(f"{'='*50}\n")

# Check required variables
print(f"{BOLD}1. Required API Keys:{RESET}")
required_vars = ['GROQ_API_KEY', 'CHROMA_API_KEY', 'CHROMA_TENANT', 'CHROMA_DATABASE', 'HF_API_TOKEN']
all_required_ok = True
for var in required_vars:
    if not check_var(var, required=True):
        all_required_ok = False

print(f"\n{BOLD}2. Flask Configuration:{RESET}")
flask_vars = ['FLASK_SECRET_KEY', 'ADMIN_API_KEY']
for var in flask_vars:
    check_var(var, required=True)

print(f"\n{BOLD}3. Optional Configuration:{RESET}")
optional_vars = ['NEXT_PUBLIC_API_URL', 'RATE_LIMIT_PER_MINUTE']
for var in optional_vars:
    check_var(var, required=False)

print(f"\n{'='*50}")

# Summary
if all_required_ok:
    print(f"\n{GREEN}{BOLD}✅ All required API keys are configured!{RESET}\n")
    
    # Test connectivity
    print(f"{BOLD}4. Testing Connectivity:{RESET}\n")
    
    # Test Groq
    print(f"  Testing Groq API...")
    try:
        import requests
        response = requests.get(
            "https://api.groq.com/openai/v1/models",
            headers={"Authorization": f"Bearer {os.environ['GROQ_API_KEY']}"},
            timeout=5
        )
        if response.status_code == 200:
            print(f"  {GREEN}✅ Groq API: Connected{RESET}")
        else:
            print(f"  {RED}❌ Groq API: Authentication failed (status {response.status_code}){RESET}")
    except Exception as e:
        print(f"  {RED}❌ Groq API: {str(e)}{RESET}")
    
    # Test HuggingFace
    print(f"\n  Testing HuggingFace API...")
    try:
        response = requests.get(
            "https://huggingface.co/api/whoami-v2",
            headers={"Authorization": f"Bearer {os.environ['HF_API_TOKEN']}"},
            timeout=5
        )
        if response.status_code == 200:
            print(f"  {GREEN}✅ HuggingFace API: Connected{RESET}")
        else:
            print(f"  {RED}❌ HuggingFace API: Authentication failed (status {response.status_code}){RESET}")
    except Exception as e:
        print(f"  {RED}❌ HuggingFace API: {str(e)}{RESET}")
    
    # Test Chroma Cloud
    print(f"\n  Testing Chroma Cloud...")
    try:
        import chromadb
        client = chromadb.HttpClient(
            host="api.trychroma.com",
            port=443,
            ssl=True,
            headers={"Authorization": f"Bearer {os.environ['CHROMA_API_KEY']}"},
            tenant=os.environ['CHROMA_TENANT'],
            database=os.environ['CHROMA_DATABASE']
        )
        collections = client.list_collections()
        print(f"  {GREEN}✅ Chroma Cloud: Connected ({len(collections)} collections){RESET}")
    except Exception as e:
        print(f"  {RED}❌ Chroma Cloud: {str(e)}{RESET}")
    
    print(f"\n{GREEN}{BOLD}🎉 Setup Complete! You're ready to run the pipeline.{RESET}\n")
    print(f"Next steps:")
    print(f"  1. Run scraper: python phases/phase_4_scheduler/main.py --mode full")
    print(f"  2. Chunk data:   python phases/phase_4_1_chunking/main.py --mode full")
    print(f"  3. Embed chunks: python phases/phase_4_2_embedding/main.py --mode embed")
    print(f"  4. Index to DB:  python phases/phase_4_3_indexing/main.py --mode upsert")
    print(f"  5. Start server: python app.py\n")
    
else:
    print(f"\n{RED}{BOLD}❌ Some required API keys are missing!{RESET}\n")
    print(f"{YELLOW}Please edit backend/.env and add your API keys.{RESET}\n")
    print(f"Get your keys from:")
    print(f"  - Groq:          https://console.groq.com/keys")
    print(f"  - Chroma Cloud:  https://www.trychroma.com/")
    print(f"  - HuggingFace:   https://huggingface.co/settings/tokens")
    print(f"\nSee API_KEYS_GUIDE.md for detailed setup instructions.\n")
    sys.exit(1)
