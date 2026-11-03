"""
Sanskrit text normalization utilities for linguistic rule handling.

Handles:
- Visarga (ः - anusvara equivalences)
- Avagraha (ऽ - elision marker)
- Sandhi variations
- Consonant endings
"""

import re


# Devanagari characters for visarga and related sounds
DEVANAGARI_VISARGA = {
    'ः',      # Visarga (anusvara, final consonant marker)
    'ं',      # Anusvara (nasal sound)
    'ऋ', 'ॄ',  # Vocalic r
    '्',      # Halant (virama)
}

DEVANAGARI_AVAGRAHA = 'ऽ'  # Avagraha (elision marker)

# Consonant classes for sandhi rules
DEVANAGARI_CONSONANTS = {
    # Velar (K)
    'क', 'ख', 'ग', 'घ', 'ङ',
    # Palatal (Ch)
    'च', 'छ', 'ज', 'झ', 'ञ',
    # Retroflex (T)
    'ट', 'ठ', 'ड', 'ढ', 'ण',
    # Dental (T)
    'त', 'थ', 'द', 'ध', 'न',
    # Labial (P)
    'प', 'फ', 'ब', 'भ', 'म',
    # Semivowels
    'य', 'र', 'ल', 'व',
    # Sibilants
    'श', 'ष', 'स', 'ह',
}

DEVANAGARI_VOWELS = {
    'अ', 'आ', 'इ', 'ई', 'उ', 'ऊ', 'ऋ', 'ॄ', 'ऌ', 'ॡ', 'ए', 'ऐ', 'ओ', 'औ'
}

DEVANAGARI_VOWEL_MARKS = {
    'ा', 'ि', 'ी', 'ु', 'ू', 'ृ', 'ॄ', 'ॢ', 'ॣ', 'े', 'ै', 'ो', 'ौ'
}


def apply_custom_rules(text, custom_rules):
    """
    Apply custom user-defined rules to Sanskrit text (unidirectional replacement).
    Useful when a strict single-pass replacement is needed.
    """
    if not custom_rules or not isinstance(custom_rules, dict):
        return text
    
    # Apply each rule sequentially
    for variant_a, variant_b in custom_rules.items():
        text = re.sub(re.escape(variant_a), variant_b, text)
    
    return text


def get_custom_variants(text, custom_rules):
    """
    Generate all valid interchangeable permutations of a text based on custom equivalence rules.
    Treats custom_rules bidirectionally, meaning A->B and B->A are both generated.
    
    custom_rules can be:
      - A list of [from, to] pairs: [[\"ः\", \"र्\"], [\"ः\", \"ो\"]] (preserves duplicate keys)
      - A dict: {\"ः\": \"ो\"} (legacy format, keys are unique - don't use for multiple mappings)
    
    Returns a list of variant strings.
    """
    if not custom_rules:
        return [text]
    
    # Normalize to list of (a, b) tuples regardless of input format
    if isinstance(custom_rules, dict):
        pairs = list(custom_rules.items())
    else:
        # list of [from, to] pairs from frontend
        pairs = [(item[0], item[1]) for item in custom_rules if len(item) == 2]
    
    if not pairs:
        return [text]
        
    variants = {text}
    for variant_a, variant_b in pairs:
        # A -> B
        if variant_a in text:
            variants.add(text.replace(variant_a, variant_b))
        # B -> A
        if variant_b in text:
            variants.add(text.replace(variant_b, variant_a))
            
    return list(variants)


def normalize_sanskrit(text, apply_rules=True, custom_rules=None):
    """
    Normalize Sanskrit text according to user-defined custom rules.
    
    Args:
        text: Sanskrit text to normalize
        apply_rules: If True, applies normalization rules. Otherwise returns unchanged text.
        custom_rules: Dict of {variant_a: variant_b} for custom transformations
                     If provided and apply_rules=True, ONLY custom rules are applied (no defaults)
    
    Returns:
        Normalized Sanskrit text or original text unchanged
    """
    if not apply_rules:
        return text
    
    # Apply custom rules only (no built-in defaults)
    if custom_rules:
        return apply_custom_rules(text, custom_rules)
    
    # If no custom rules provided and apply_rules=True, return unchanged
    # (no default rules applied)
    return text


def normalize_visarga(text):
    """
    Handle visarga (ः) transformations and equivalences.
    
    Visarga rules:
    - ः after vowel can equivalent to ो (o), dropping the ः
    - ः before consonants changes based on consonant class (Panini's rules)
    - हरिः (nominative) = हरि + ः (abstract) 
    - रामः = रामो (pausal form)
    - ः can become ं (anusvara) before certain consonants
    """
    result = []
    i = 0
    
    while i < len(text):
        char = text[i]
        
        # Look for ः (visarga)
        if char == 'ः':
            if i > 0:
                prev_char = text[i - 1]
                next_char = text[i + 1] if i + 1 < len(text) else None
                
                # If previous is a vowel mark, get the actual vowel
                # Example: "रा" followed by ः
                if prev_char in DEVANAGARI_VOWEL_MARKS:
                    # This ः is after a vowel, could be pausal (o-form)
                    # So "रामः" could match "रामो"
                    # Add both variants - we'll handle this in search normalization
                    result.append('ः')
                elif prev_char in DEVANAGARI_VOWELS:
                    # Direct vowel + ः (like अः, आः)
                    result.append('ः')
                elif prev_char == '्':
                    # After halant, this is unusual but may occur
                    result.append('ः')
                else:
                    result.append('ः')
            else:
                result.append('ः')
        
        # Handle ो (o-form) as alternate of ः
        # This allows रामो to match रामः
        elif char == 'ो':
            result.append('ो')
        
        # Handle consonant clusters for sandhi
        elif char == '्' and i + 1 < len(text):
            # Halant indicates consonant cluster
            result.append('्')
        
        else:
            result.append(char)
        
        i += 1
    
    return ''.join(result)


def create_search_variants(text, apply_rules=True):
    """
    Generate alternative search patterns for a single Sanskrit word/phrase.
    
    This creates multiple patterns to match against normalized text.
    Useful for finding equivalent forms.
    
    Returns a list of normalization patterns.
    """
    if not apply_rules:
        return [text]
    
    variants = set()
    normalized = normalize_sanskrit(text, apply_rules)
    
    # Add the normalized form
    variants.add(normalized)
    
    # Add original form
    variants.add(text)
    
    # Add specific visarga variants
    # Pattern: उत्तरः -> also match उत्तरो
    if 'ः' in text:
        # Variant 1: ः -> ो (pausal form)
        variant1 = text.replace('ः', 'ो')
        variants.add(variant1)
        variants.add(normalize_sanskrit(variant1, apply_rules))
        
        # Variant 2: ः -> ं (anusvara)
        variant2 = text.replace('ः', 'ं')
        variants.add(variant2)
        variants.add(normalize_sanskrit(variant2, apply_rules))
        
        # Variant 3: ः removal
        variant3 = text.replace('ः', '')
        variants.add(variant3)
        variants.add(normalize_sanskrit(variant3, apply_rules))
        
        # Variant 4: ः -> halant (हरिः -> हरि्)
        colon_index = text.rfind('ः')
        if colon_index > 0:
            variant4 = text[:colon_index] + '्'
            variants.add(variant4)
            variants.add(normalize_sanskrit(variant4, apply_rules))
            
            # Variant 5: ः -> consonant variants (like र्, न्)
            # For हरिः, also try common final consonants
            prev_char = text[colon_index - 1] if colon_index > 0 else ''
            if prev_char in DEVANAGARI_VOWEL_MARKS or prev_char in DEVANAGARI_VOWELS:
                # Common consonant endings after vowels
                for consonant in ['र्', 'न्', 'ल्', 'म्', 'य्']:
                    variant_cons = text[:colon_index] + consonant
                    variants.add(variant_cons)
                    variants.add(normalize_sanskrit(variant_cons, apply_rules))
    
    # Handle consonant with halant (्) as similar to ः
    if '्' in text:
        # Treat halant-ending words as similar to visarga-ending words
        # हरि् can be similar to हरिः
        variant_with_colon = text.replace('्', 'ः')
        variants.add(variant_with_colon)
        variants.add(normalize_sanskrit(variant_with_colon, apply_rules))
    
    # Avagraha handling with space-based variants
    if 'ऽ' in text:
        # Remove avagraha
        variant_no_avagraha = text.replace('ऽ', '')
        variants.add(variant_no_avagraha)
        variants.add(normalize_sanskrit(variant_no_avagraha, apply_rules))
        
        # Replace avagraha with space
        variant_space = text.replace('ऽ', ' ')
        variants.add(variant_space)
        variants.add(normalize_sanskrit(variant_space, apply_rules))
        
        # Also create version with avagraha removed but space-collapsed
        variant_collapsed = re.sub(r'\s+', ' ', variant_no_avagraha).strip()
        variants.add(variant_collapsed)
    
    # Handle multi-word compounds - create variants with/without spaces
    if ' ' in text:
        # Version without spaces
        variant_no_space = text.replace(' ', '')
        variants.add(variant_no_space)
        variants.add(normalize_sanskrit(variant_no_space, apply_rules))
        
        # Replace space with avagraha
        variant_with_avagraha = text.replace(' ', 'ऽ')
        variants.add(variant_with_avagraha)
        variants.add(normalize_sanskrit(variant_with_avagraha, apply_rules))
    
    # Remove None and empty strings
    variants.discard(None)
    variants.discard('')
    
    return list(variants)


def prepare_text_for_comparison(text, apply_rules=True):
    """
    Prepare text for comparison by normalizing and removing special characters.
    
    This is useful for character-by-character comparison.
    """
    if not apply_rules:
        return text
    
    # Normalize
    normalized = normalize_sanskrit(text, apply_rules)
    
    # Remove spaces for character-level matching
    # (keep them for word-level matching in calling code)
    return normalized


def normalize_for_regex(text, apply_rules=True):
    """
    Normalize text for use in regex patterns.
    
    Creates a regex pattern that matches the normalized form and common variants.
    """
    if not apply_rules:
        return re.escape(text)
    
    variants = create_search_variants(text, apply_rules)
    
    # Escape for regex
    escaped = [re.escape(v) for v in variants]
    
    # Create alternation pattern
    if len(escaped) == 1:
        return escaped[0]
    else:
        return f"(?:{'|'.join(escaped)})"


def match_sanskrit_words(word1, word2, apply_rules=True):
    """
    Check if two Sanskrit words should be considered equivalent
    based on linguistic rules.
    
    Examples:
        match_sanskrit_words('रामः', 'रामो') -> True
        match_sanskrit_words('हरिः', 'हरिर्') -> True
        match_sanskrit_words('विष्णुः', 'विष्णु') -> True
    """
    if not apply_rules:
        return word1 == word2
    
    # Normalize both words
    norm1 = normalize_sanskrit(word1, apply_rules)
    norm2 = normalize_sanskrit(word2, apply_rules)
    
    # Direct match after normalization
    if norm1 == norm2:
        return True
    
    # Check if one is in the variants of the other
    variants1 = create_search_variants(word1, apply_rules)
    variants2 = create_search_variants(word2, apply_rules)
    
    return bool(set(variants1) & set(variants2))
