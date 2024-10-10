import json
import gzip
import base64

def compress_json(json_data):
    # Convert JSON to string
    json_string = json.dumps(json_data, separators=(',', ':'))
    
    # Compress the string
    compressed = gzip.compress(json_string.encode('utf-8'))
    
    # Encode to base64 for easy storage/transmission
    return base64.b64encode(compressed).decode('ascii')

def decompress_json(compressed_data):
    # Decode from base64
    decoded = base64.b64decode(compressed_data)
    
    # Decompress
    decompressed = gzip.decompress(decoded)
    
    # Parse JSON
    return json.loads(decompressed)