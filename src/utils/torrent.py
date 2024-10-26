import re
from urllib.parse import urlparse, parse_qs

def extract_infohash(magnet_link):
    # Check if the input is a valid magnet link
    if not magnet_link.startswith('magnet:?'):
        raise ValueError("Invalid magnet link format")

    # Parse the magnet link
    parsed = urlparse(magnet_link)
    params = parse_qs(parsed.query)

    # Look for the 'xt' parameter
    xt_params = params.get('xt', [])
    for xt in xt_params:
        # Check if it's a BitTorrent info hash
        if xt.startswith('urn:btih:'):
            # Extract the info hash
            infohash = xt.split(':')[-1].lower()
            
            # Validate the infohash
            if re.match(r'^[0-9a-f]{40}$', infohash):
                return infohash
            elif re.match(r'^[0-9a-z]{32}$', infohash):
                # It's a base32 encoded infohash
                return infohash
    
    raise ValueError("No valid BitTorrent info hash found in the magnet link")


def get_type_and_infohash(input_string):
    # Check if it's a magnet link
    if input_string.startswith('magnet:?'):
        try:
            infohash = extract_infohash(input_string)
            return "Magnet Link", infohash
        except ValueError:
            return "Invalid Magnet Link", None

    # Check if it's a SHA-1 infohash (40 hexadecimal characters)
    if re.match(r'^[0-9a-fA-F]{40}$', input_string):
        return "Infohash (SHA-1)", input_string.lower()

    # Check if it's a base32 encoded infohash (32 alphanumeric characters)
    if re.match(r'^[0-9a-zA-Z]{32}$', input_string):
        return "Infohash (Base32)", input_string.lower()

    # If it's neither
    return "Unknown", None