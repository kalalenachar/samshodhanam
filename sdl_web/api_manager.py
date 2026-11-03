import json
import os
import secrets
import hashlib
from datetime import datetime
from time_utils import get_ist_now

API_KEYS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'api_keys.json')

def load_keys():
    if not os.path.exists(API_KEYS_FILE):
        return {}
    try:
        with open(API_KEYS_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
            return data.get('keys', {})
    except:
        return {}

def save_keys(keys):
    try:
        data = {
            "metadata": {
                "version": "1.0",
                "last_updated": get_ist_now().isoformat()
            },
            "keys": keys
        }
        with open(API_KEYS_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4)
        return True
    except:
        return False

def generate_api_key():
    """Generate a new random API key."""
    return f"sdl_live_{secrets.token_hex(24)}"

def hash_key(key):
    """Hash a key for secure storage."""
    return hashlib.sha256(key.encode()).hexdigest()

def create_key(label, permissions=None):
    """Create a new API key and store its hash."""
    keys = load_keys()
    raw_key = generate_api_key()
    key_hash = hash_key(raw_key)
    
    keys[key_hash] = {
        "label": label,
        "permissions": permissions or ["READ"],
        "created_at": get_ist_now().isoformat(),
        "last_used": None,
        "active": True
    }
    
    if save_keys(keys):
        return raw_key # Return the raw key ONLY once
    return None

def validate_key(key):
    """Check if an API key is valid and return its permissions."""
    if not key:
        return None
    
    key_hash = hash_key(key)
    keys = load_keys()
    
    if key_hash in keys and keys[key_hash].get('active', True):
        # Update last used timestamp (async-ish/lazy)
        keys[key_hash]['last_used'] = get_ist_now().isoformat()
        save_keys(keys)
        return keys[key_hash]
    
    return None

def revoke_key(key_hash):
    """Deactivate an API key."""
    keys = load_keys()
    if key_hash in keys:
        keys[key_hash]['active'] = False
        return save_keys(keys)
    return False

def delete_key(key_hash):
    """Permanently remove an API key."""
    keys = load_keys()
    if key_hash in keys:
        del keys[key_hash]
        return save_keys(keys)
    return False

# =============================================================================
# SUGGESTIONS HANDLING
# =============================================================================

API_SUGGESTIONS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'api_suggestions.json')

def load_suggestions():
    if not os.path.exists(API_SUGGESTIONS_FILE):
        return []
    try:
        with open(API_SUGGESTIONS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except:
        return []

def save_suggestion(key_label, content):
    """Save a suggestion from an API user."""
    suggestions = load_suggestions()
    suggestions.append({
        "from": key_label,
        "content": content,
        "timestamp": get_ist_now().isoformat(),
        "status": "pending"
    })
    try:
        with open(API_SUGGESTIONS_FILE, 'w', encoding='utf-8') as f:
            json.dump(suggestions, f, indent=4)
        return True
    except:
        return False

def clear_suggestions():
    """Clear all suggestions."""
    try:
        if os.path.exists(API_SUGGESTIONS_FILE):
            os.remove(API_SUGGESTIONS_FILE)
        return True
    except:
        return False
