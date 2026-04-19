"""Test Chroma Cloud connection"""
import os
from dotenv import load_dotenv
import chromadb

load_dotenv()

api_key = os.environ.get("CHROMA_API_KEY", "")
tenant = os.environ.get("CHROMA_TENANT", "")
database = os.environ.get("CHROMA_DATABASE", "")

print(f"Testing Chroma Cloud connection...")
print(f"API Key: {api_key[:20]}...")
print(f"Tenant: {tenant}")
print(f"Database: {database}")
print()

try:
    client = chromadb.HttpClient(
        host="api.trychroma.com",
        port=443,
        ssl=True,
        headers={"Authorization": f"Bearer {api_key}"},
        tenant=tenant,
        database=database
    )
    
    print("✅ Connection successful!")
    print()
    
    # List collections
    collections = client.list_collections()
    print(f"📚 Found {len(collections)} collections:")
    for col in collections:
        print(f"   - {col.name}")
        
except Exception as e:
    print(f"❌ Connection failed: {e}")
    print()
    print("Possible issues:")
    print("  1. API key is invalid or expired")
    print("  2. Tenant ID doesn't exist")
    print("  3. Database doesn't exist")
    print("  4. Network/firewall blocking connection")
    print()
    print("Visit https://www.trychroma.com/ to verify your credentials")
