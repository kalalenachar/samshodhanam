"""
Samshodhanam Multiscript Transliteration Engine.
Matches the exact phoneme table and conversion logic of the web app (transliterator.html).
Supports Devanagari, Kannada, Telugu, Tamil (with superscripts ² ³ ⁴ and Grantha), Malayalam,
IAST, ITRANS, and SLP1.
"""

import re
from typing import Dict, List, Optional, Tuple, Any

SCRIPTS = ['sa', 'ka', 'te', 'ta', 'en', 'itrans', 'slp1', 'ml', 'bn', 'gu']

SCRIPT_NAMES = {
    'sa': 'Sanskrit (Devanagari)',
    'ka': 'Kannada',
    'te': 'Telugu',
    'ta': 'Tamil (Enhanced)',
    'en': 'English (IAST)',
    'itrans': 'ITRANS',
    'slp1': 'SLP1',
    'ml': 'Malayalam',
    'bn': 'Bengali',
    'gu': 'Gujarati'
}

# Phoneme Table matching web app (sa, ka, te, ta, en)
PHONEME_TABLE = [
    # Independent Vowels (0-13)
    ['अ', 'ಅ', 'అ', 'அ', 'a'],
    ['आ', 'ಆ', 'ఆ', 'ஆ', 'ā'],
    ['इ', 'ಇ', 'ఇ', 'இ', 'i'],
    ['ई', 'ಈ', 'ఈ', 'ஈ', 'ī'],
    ['उ', 'ಉ', 'ఉ', 'உ', 'u'],
    ['ऊ', 'ಊ', 'ఊ', 'ஊ', 'ū'],
    ['ऋ', 'ಋ', 'ఋ', 'ரு', 'ṛ'],
    ['ॠ', 'ೠ', 'ౠ', 'ரூ', 'ṝ'],
    ['ऌ', 'ಌ', 'ఌ', 'லு', 'ḷ'],
    ['ॡ', 'ೡ', 'ౡ', 'லூ', 'ḹ'],
    ['ए', 'ಏ', 'ఏ', 'ஏ', 'ē'],
    ['ऐ', 'ಐ', 'ఐ', 'ஐ', 'ai'],
    ['ओ', 'ಓ', 'ఓ', 'ஓ', 'ō'],
    ['औ', 'ಔ', 'ఔ', 'ஔ', 'au'],
    # Dependent Vowel Signs (14-26)
    ['ा', 'ಾ', 'ా', 'ா', 'ā'],
    ['ि', 'ಿ', 'ి', 'ி', 'i'],
    ['ी', 'ೀ', 'ీ', 'ீ', 'ī'],
    ['ु', 'ು', 'ు', 'ு', 'u'],
    ['ू', 'ೂ', 'ూ', 'ூ', 'ū'],
    ['ृ', 'ೃ', 'ృ', '்ரு', 'ṛ'],
    ['ॄ', 'ೄ', 'ౄ', '்ரூ', 'ṝ'],
    ['ॢ', 'ೢ', 'ౢ', '்லு', 'ḷ'],
    ['ॣ', 'ೣ', 'ౣ', '்லூ', 'ḹ'],
    ['े', 'ೇ', 'ే', 'ே', 'ē'],
    ['ै', 'ೈ', 'ై', 'ை', 'ai'],
    ['ो', 'ೋ', 'ో', 'ோ', 'ō'],
    ['ौ', 'ೌ', 'ౌ', 'ௌ', 'au'],
    # Halant/Virama (27)
    ['्', '್', '్', '்', ''],
    # Anusvara, Visarga (28,29)
    ['ं', 'ಂ', 'ం', 'ம்', 'ṃ'],
    ['ः', 'ಃ', 'ః', 'ஃ', 'ḥ'],
    # ── ka-varga ── (30-34)
    ['क', 'ಕ', 'క', 'க', 'k'],
    ['ख', 'ಖ', 'ఖ', 'க²', 'kh'],
    ['ग', 'ಗ', 'గ', 'க³', 'g'],
    ['घ', 'ಘ', 'ఘ', 'க⁴', 'gh'],
    ['ङ', 'ಙ', 'ఙ', 'ங', 'ṅ'],
    # ── ca-varga ── (35-39)
    ['च', 'ಚ', 'చ', 'ச', 'c'],
    ['छ', 'ಛ', 'ఛ', 'ச²', 'ch'],
    ['ज', 'ಜ', 'జ', 'ஜ', 'j'],
    ['झ', 'ಝ', 'ఝ', 'ஜ²', 'jh'],
    ['ञ', 'ಞ', 'ఞ', 'ஞ', 'ñ'],
    # ── ṭa-varga ── (40-44)
    ['ट', 'ಟ', 'ట', 'ட', 'ṭ'],
    ['ठ', 'ಠ', 'ఠ', 'ட²', 'ṭh'],
    ['ड', 'ಡ', 'డ', 'ட³', 'ḍ'],
    ['ढ', 'ಢ', 'ఢ', 'ட⁴', 'ḍh'],
    ['ण', 'ಣ', 'ణ', 'ண', 'ṇ'],
    # ── ta-varga ── (45-49)
    ['त', 'ತ', 'త', 'த', 't'],
    ['थ', 'ಥ', 'థ', 'த²', 'th'],
    ['द', 'ದ', 'ద', 'த³', 'd'],
    ['ध', 'ಧ', 'ధ', 'த⁴', 'dh'],
    ['न', 'ನ', 'న', 'ந', 'n'],
    # ── pa-varga ── (50-54)
    ['प', 'ಪ', 'ప', 'ப', 'p'],
    ['फ', 'ಫ', 'ఫ', 'ப²', 'ph'],
    ['ब', 'ಬ', 'బ', 'ப³', 'b'],
    ['भ', 'ಭ', 'భ', 'ப⁴', 'bh'],
    ['म', 'ಮ', 'మ', 'ம', 'm'],
    # ── avarga / semi-vowels ── (55-58)
    ['य', 'ಯ', 'య', 'ய', 'y'],
    ['र', 'ರ', 'ర', 'ர', 'r'],
    ['ल', 'ಲ', 'ల', 'ல', 'l'],
    ['व', 'ವ', 'వ', 'வ', 'v'],
    # ── sibilants & ha ── (59-62)
    ['श', 'ಶ', 'శ', 'ஶ', 'ś'],
    ['ष', 'ಷ', 'ష', 'ஷ', 'ṣ'],
    ['स', 'ಸ', 'స', 'ஸ', 's'],
    ['ह', 'ಹ', 'హ', 'ஹ', 'h'],
    # ── special ── (63)
    ['ळ', 'ಳ', 'ళ', 'ள', 'ḷ'],
    # Numbers (64-73)
    ['०', '೦', '౦', '௦', '0'],
    ['१', '೧', '౧', '௧', '1'],
    ['२', '೨', '౨', '௨', '2'],
    ['३', '೩', '౩', '௩', '3'],
    ['४', '೪', '౪', '௪', '4'],
    ['५', '೫', '౫', '௫', '5'],
    ['६', '೬', '౬', '௬', '6'],
    ['७', '೭', '౭', '௭', '7'],
    ['८', '೮', '౮', '௮', '8'],
    ['९', '೯', '౯', '௯', '9'],
    # Short-e, short-o variants
    ['ऎ', 'ಎ', 'ఎ', 'எ', 'e'],
    ['ॆ', 'ೆ', 'ె', 'ெ', 'e'],
    ['ऒ', 'ಒ', 'ఒ', 'ஒ', 'o'],
    ['ॊ', 'ೊ', 'ొ', 'ொ', 'o'],
    # Om (78)
    ['ॐ', 'ಓಂ', 'ఓం', 'ஓம்', 'oṃ'],
    # Avagraha (79)
    ['ऽ', 'ಽ', 'ఽ', 'ऽ', '\''],
    # Chandrabindu (80)
    ['ँ', 'ಁ', 'ఁ', 'ஂ', 'm̐'],
    # Danda & Double Danda (81-82)
    ['।', '।', '।', '।', '|'],
    ['॥', '॥', '॥', '॥', '||'],
]

# Build char to index and index to char maps
char_to_idx: List[Dict[str, int]] = [{} for _ in range(5)]
idx_to_char: List[Dict[int, str]] = [{} for _ in range(5)]

for row_idx, row in enumerate(PHONEME_TABLE):
    for s_idx in range(5):
        ch = row[s_idx]
        if ch is not None:
            if len(ch) > 0 and ch not in char_to_idx[s_idx]:
                char_to_idx[s_idx][ch] = row_idx
            if row_idx not in idx_to_char[s_idx]:
                idx_to_char[s_idx][row_idx] = ch

# Aliases for alternate representations and Devanagari OCR/nukta variants
if 'ௐ' not in char_to_idx[3] and 'ॐ' in char_to_idx[0]:
    char_to_idx[3]['ௐ'] = char_to_idx[0]['ॐ']
if "'" not in char_to_idx[3] and 'ऽ' in char_to_idx[0]:
    char_to_idx[3]["'"] = char_to_idx[0]['ऽ']
if '’' not in char_to_idx[3] and 'ऽ' in char_to_idx[0]:
    char_to_idx[3]['’'] = char_to_idx[0]['ऽ']
if '‘' not in char_to_idx[3] and 'ऽ' in char_to_idx[0]:
    char_to_idx[3]['‘'] = char_to_idx[0]['ऽ']
if '’' not in char_to_idx[4] and 'ऽ' in char_to_idx[0]:
    char_to_idx[4]['’'] = char_to_idx[0]['ऽ']
if '‘' not in char_to_idx[4] and 'ऽ' in char_to_idx[0]:
    char_to_idx[4]['‘'] = char_to_idx[0]['ऽ']
if '.' not in char_to_idx[4] and '।' in char_to_idx[0]:
    char_to_idx[4]['.'] = char_to_idx[0]['।']

sa_aliases = {
    'क़': 'क', 'ख़': 'ख', 'ग़': 'ग', 'ज़': 'ज', 'ड़': 'ड', 'ढ़': 'ढ',
    'फ़': 'फ', 'य़': 'य', 'ऩ': 'न', 'ऱ': 'र', 'ऴ': 'ळ', 'ऄ': 'अ',
    'ऍ': 'ए', 'ॅ': 'े', 'ऑ': 'ओ', 'ॉ': 'ो', 'ॲ': 'अ', 'ऀ': 'ँ',
    'ॎ': 'े', 'ॏ': 'ौ', '॰': '।'
}
for k, v in sa_aliases.items():
    if k not in char_to_idx[0] and v in char_to_idx[0]:
        char_to_idx[0][k] = char_to_idx[0][v]

# Tamil multi-character tokens (longest first)
tamil_multi_tokens = []
for row in PHONEME_TABLE:
    ch = row[3]  # Tamil column
    if ch and len(ch) > 1 and ch not in tamil_multi_tokens:
        tamil_multi_tokens.append(ch)
tamil_multi_tokens.sort(key=lambda x: len(x), reverse=True)

# IAST multi-character tokens (longest first)
iast_seq = [
    'oṃ', 'm̐', '||', 'ā', 'ī', 'ū', 'ē', 'ō', 'ṛ', 'ṝ', 'ḷ', 'ḹ', 'ai', 'au',
    'e', 'o', 'i', 'u', 'ṃ', 'ḥ', 'ṅ', 'ñ', 'ṭh', 'ḍh', 'ṭ', 'ḍ', 'ṇ',
    'ś', 'ṣ', 'kh', 'gh', 'ch', 'jh', 'th', 'dh', 'ph', 'bh'
]
iast_seq.sort(key=lambda x: len(x), reverse=True)

def detect_script(text: str) -> str:
    """Detect script from input string based on Unicode ranges."""
    devanagari_cnt = 0
    kannada_cnt = 0
    telugu_cnt = 0
    tamil_cnt = 0
    malayalam_cnt = 0
    
    for ch in text:
        cp = ord(ch)
        if 0x0900 <= cp <= 0x097F:
            devanagari_cnt += 1
        elif 0x0C80 <= cp <= 0x0CFF:
            kannada_cnt += 1
        elif 0x0C00 <= cp <= 0x0C7F:
            telugu_cnt += 1
        elif 0x0B80 <= cp <= 0x0BFF:
            tamil_cnt += 1
        elif 0x0D00 <= cp <= 0x0D7F:
            malayalam_cnt += 1
            
    counts = [
        (devanagari_cnt, 'sa'),
        (kannada_cnt, 'ka'),
        (telugu_cnt, 'te'),
        (tamil_cnt, 'ta'),
        (malayalam_cnt, 'ml')
    ]
    counts.sort(key=lambda x: x[0], reverse=True)
    if counts[0][0] > 0:
        return counts[0][1]
    
    # Check IAST / Latin diacritics
    if any(c in text for c in 'āīūṛṝḷḹēōṃḥṅñṭḍṇśṣ'):
        return 'en'
    
    return 'sa'  # Default to Sanskrit Devanagari

SCRIPT_RANGES = {
    'sa': (0x0900, 0x097F),
    'ka': (0x0C80, 0x0CFF),
    'te': (0x0C00, 0x0C7F),
    'ta': (0x0B80, 0x0BFF)
}

def is_vedic_accent(code: int) -> bool:
    return code == 0x0951 or code == 0x0952 or (0x1CD0 <= code <= 0x1CF9) or (0xA8E0 <= code <= 0xA8F1)

def is_script_mismatch(orig_word: str, converted_word: str, from_script: str, to_script: str) -> bool:
    if to_script == from_script:
        return False
    
    # 1. Did source script characters leak through into converted_word?
    if from_script in SCRIPT_RANGES and to_script != from_script:
        start, end = SCRIPT_RANGES[from_script]
        for ch in converted_word:
            cp = ord(ch)
            if is_vedic_accent(cp):
                continue
            if cp in (0x0964, 0x0965, 0x093D):
                continue
            if start <= cp <= end:
                return True
    
    # 2. If to_script is Indic, did characters from another foreign Indic script leak through?
    if to_script in SCRIPT_RANGES:
        for s, (o_start, o_end) in SCRIPT_RANGES.items():
            if s != to_script:
                for ch in converted_word:
                    cp = ord(ch)
                    if is_vedic_accent(cp):
                        continue
                    if cp in (0x0964, 0x0965, 0x093D):
                        continue
                    if o_start <= cp <= o_end:
                        return True
                        
    return False

def apply_language_varga_panchama(text: str, target_script: str) -> str:
    if not text:
        return text
    if target_script == 'ka':
        text = re.sub(r'ಙ್(?=[ಕಖಗಘ])', 'ಂ', text)
        text = re.sub(r'ಞ್(?=[ಚಛಜಝ])', 'ಂ', text)
        text = re.sub(r'ಣ್(?=[ಟಠಡಢ])', 'ಂ', text)
        text = re.sub(r'ನ್(?=[ತಥದಧ])', 'ಂ', text)
        text = re.sub(r'ಮ್(?=[ಪಫಬಭ])', 'ಂ', text)
    elif target_script == 'te':
        text = re.sub(r'ఙ్(?=[కఖగఘ])', 'ం', text)
        text = re.sub(r'ఞ్(?=[చఛజఝ])', 'ం', text)
        text = re.sub(r'ణ్(?=[టఠడఢ])', 'ం', text)
        text = re.sub(r'న్(?=[తథదధ])', 'ం', text)
        text = re.sub(r'మ్(?=[పఫబభ])', 'ం', text)
    elif target_script == 'ta':
        text = re.sub(r'ம்(?=க[²³⁴]?)', 'ங்', text)
        text = re.sub(r'ம்(?=[சஜ][²³⁴]?)', 'ஞ்', text)
        text = re.sub(r'ம்(?=ட[²³⁴]?)', 'ண்', text)
        text = re.sub(r'ம்(?=த[²³⁴]?)', 'ந்', text)
        text = re.sub(r'ம்(?=ப[²³⁴]?)', 'ம்', text)
    return text

def _convert_raw_tokens(text: str, from_script: str, to_script: str) -> str:
    from_idx = SCRIPTS.index(from_script)
    to_idx = SCRIPTS.index(to_script)
    
    result = []
    i = 0
    n = len(text)
    
    while i < n:
        matched = False
        
        # 1. Check multi-char tokens for Tamil (index 3)
        if from_idx == 3:
            for tok in tamil_multi_tokens:
                if text.startswith(tok, i):
                    r_idx = char_to_idx[3].get(tok)
                    if r_idx is not None:
                        out_ch = idx_to_char[to_idx].get(r_idx, tok)
                        result.append(out_ch)
                        i += len(tok)
                        matched = True
                        break
            if matched:
                continue
                
        # 2. Check multi-char tokens for IAST (index 4)
        if from_idx == 4:
            for seq in iast_seq:
                if text.startswith(seq, i):
                    r_idx = char_to_idx[4].get(seq)
                    if r_idx is not None:
                        out_ch = idx_to_char[to_idx].get(r_idx, seq)
                        result.append(out_ch)
                        i += len(seq)
                        matched = True
                        break
            if matched:
                continue
                
        ch = text[i]
        code = ord(ch)

        # Preserve Vedic accents directly (insert before Tamil superscripts to prevent dotted-circle breakage)
        if is_vedic_accent(code):
            if to_script == 'ta' and len(result) > 0 and (result[-1] in '²³⁴' or result[-1].endswith(('²', '³', '⁴'))):
                superscript = result[-1][-1]
                result[-1] = result[-1][:-1]
                if not result[-1]:
                    result.pop()
                result.append(ch)
                result.append(superscript)
            else:
                result.append(ch)
            i += 1
            continue

        # Handle Tamil consonant with superscript (and optional vowel sign and Vedic accents):
        # e.g. த + ே + ॒ + ³ -> de॒, த + ே + ³ -> de, த + ॒ + ³ -> da॒
        if from_idx == 3:
            row_idx = char_to_idx[3].get(ch)
            if row_idx is not None and 30 <= row_idx <= 63:
                j = i + 1
                vowel_sign = None
                vowel_row_idx = None
                superscript = None
                accents = []

                while j < n:
                    next_char = text[j]
                    next_code = ord(next_char)
                    if superscript is None and next_char in '²³⁴':
                        superscript = next_char
                        j += 1
                        continue
                    if is_vedic_accent(next_code):
                        accents.append(next_char)
                        j += 1
                        continue
                    if vowel_sign is None and superscript is None:
                        n_row_idx = char_to_idx[3].get(next_char)
                        if n_row_idx is not None and ((14 <= n_row_idx <= 27) or n_row_idx in (75, 77)):
                            vowel_sign = next_char
                            vowel_row_idx = n_row_idx
                            j += 1
                            continue
                    break

                if superscript:
                    base_char = ch + superscript
                    base_row_idx = char_to_idx[3].get(base_char)
                    if base_row_idx is not None:
                        out = PHONEME_TABLE[base_row_idx][4] if to_script == 'en' else idx_to_char[to_idx].get(base_row_idx, base_char)
                        result.append(out)
                        if to_script == 'en':
                            if vowel_row_idx is not None and ((14 <= vowel_row_idx <= 26) or vowel_row_idx in (75, 77)):
                                result.append(PHONEME_TABLE[vowel_row_idx][4])
                            elif vowel_row_idx is None:
                                result.append('a')
                        else:
                            if vowel_row_idx is not None:
                                result.append(idx_to_char[to_idx].get(vowel_row_idx, vowel_sign))
                        if accents:
                            result.extend(accents)
                        i = j
                        continue

        # Special handling for Tamil superscripts (OUTPUT to Tamil)
        if to_script == 'ta' and len(result) > 0 and (result[-1] in '²³⁴' or result[-1].endswith(('²', '³', '⁴'))):
            r_idx = char_to_idx[from_idx].get(ch)
            is_vowel_or_halant = r_idx is not None and ((14 <= r_idx <= 27) or r_idx in (75, 77))
            if is_vowel_or_halant:
                superscript = result[-1][-1]
                result[-1] = result[-1][:-1]
                if not result[-1]:
                    result.pop()

                # Check for any Vedic accents before the superscript
                accents = []
                while result and any(is_vedic_accent(ord(c)) for c in result[-1]):
                    accents.append(result.pop())
                accents.reverse()

                out_vowel = idx_to_char[to_idx].get(r_idx, ch)
                result.append(out_vowel)
                result.extend(accents)
                result.append(superscript)
                i += 1
                continue

        # 3. Check single character lookup
        r_idx = char_to_idx[from_idx].get(ch)
        if r_idx is not None:
            out_ch = idx_to_char[to_idx].get(r_idx, ch)
            result.append(out_ch)
        else:
            result.append(ch)
        i += 1
        
    return "".join(result)

def convert_word_with_fallback(word: str, from_script: str, to_script: str) -> str:
    if not word:
        return ""
    has_indic = bool(re.search(r'[\u0900-\u097F\u0C80-\u0CFF\u0C00-\u0C7F\u0B80-\u0BFF]', word))
    converted = _convert_raw_tokens(word, from_script, to_script)
    converted = apply_language_varga_panchama(converted, to_script)
    # Only wrap in brackets if target is English/IAST and unmapped characters leaked through
    if to_script == 'en' and has_indic and is_script_mismatch(word, converted, from_script, to_script):
        return f"({word})"
    return converted

def convert_script(text: str, from_script: str, to_script: str) -> str:
    """Convert text from one script to another matching transliterator.html logic."""
    if not text:
        return ""
    
    import unicodedata
    # Decompose first so combining nukta (\u093C) is detached, strip nukta, then re-compose
    text = unicodedata.normalize('NFD', text).replace('\u093c', '').replace('\u093C', '')
    text = unicodedata.normalize('NFC', text)
    
    if from_script == 'auto':
        from_script = detect_script(text)
        
    if from_script == to_script:
        return text
    
    # Fallback to vidyut / indic-transliteration if using extended schemes (slp1, itrans, ml, bn, gu)
    supported_native = ['sa', 'ka', 'te', 'ta', 'en']
    if from_script not in supported_native or to_script not in supported_native:
        return _convert_via_vidyut_or_sanscript(text, from_script, to_script)
        
    tokens = re.split(r'([^\S\r\n]+|[।॥\s,;:!?"\'()[\]{}<>\/\\–—\-]+)', text)
    output = []
    for token in tokens:
        if not token:
            continue
        if re.match(r'^[।॥\s,;:!?"\'()[\]{}<>\/\\–—\-]+$', token):
            output.append(_convert_raw_tokens(token, from_script, to_script))
        else:
            output.append(convert_word_with_fallback(token, from_script, to_script))
    return "".join(output)


def _convert_via_vidyut_or_sanscript(text: str, from_script: str, to_script: str) -> str:
    """Fallback transliteration using vidyut.lipi or indic-transliteration."""
    try:
        from vidyut.lipi import Scheme, transliterate
        scheme_map = {
            'sa': Scheme.Devanagari,
            'ka': Scheme.Kannada,
            'te': Scheme.Telugu,
            'ta': Scheme.Tamil,
            'en': Scheme.Iast,
            'slp1': Scheme.Slp1,
            'itrans': Scheme.Itrans,
            'ml': Scheme.Malayalam
        }
        if from_script in scheme_map and to_script in scheme_map:
            return transliterate(text, scheme_map[from_script], scheme_map[to_script])
    except Exception:
        pass

    try:
        from indic_transliteration import sanscript
        sanscript_map = {
            'sa': sanscript.DEVANAGARI,
            'ka': sanscript.KANNADA,
            'te': sanscript.TELUGU,
            'ta': sanscript.TAMIL,
            'en': sanscript.IAST,
            'itrans': sanscript.ITRANS,
            'slp1': sanscript.SLP1,
            'ml': sanscript.MALAYALAM,
            'bn': sanscript.BENGALI,
            'gu': sanscript.GUJARATI
        }
        if from_script in sanscript_map and to_script in sanscript_map:
            return sanscript.transliterate(text, sanscript_map[from_script], sanscript_map[to_script])
    except Exception:
        pass
    
    return text
