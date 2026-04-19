import json

with open('sources.json', 'r') as f:
    data = json.load(f)

print(f"✅ Valid JSON with {len(data['sources'])} sources\n")

for i, source in enumerate(data['sources'], 1):
    print(f"{i:2}. {source['id']}")
    print(f"    URL: {source['url']}")
    print(f"    Scheme: {source['scheme']}")
    print(f"    Category: {source['category']}")
    print(f"    Type: {source['type']}")
    print()
