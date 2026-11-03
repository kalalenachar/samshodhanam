# Sanskrit Linguistic Normalization Feature

## Overview

This feature implements Sanskrit linguistic rule handling for OCR text search, allowing searches to match equivalent Sanskrit word forms based on classical Sanskrit grammar rules.

## Features Implemented

### 1. **Visarga (Anusvara) Rules**
Treats final consonant markers equivalently:
- **रामः** (rāmaḥ - masculine nominative) matches **रामो** (rāmo - pausal form)
- **हरिः** (harīḥ - nominative) matches **हरिर्** (harīr - with halant)
- ः (visarga) can be transformed to:
  - ो (o-form/pausal)
  - ं (anusvara)
  - ् (halant)
  - or removed entirely

### 2. **Avagraha (ऽ) Handling**
Treats avagraha and its omissions equivalently:
- **रामोऽस्ति** matches **रामोस्ति** (avagraha removed)
- **रामोऽस्ति** matches **रामः अस्ति** (avagraha replaced with space)

### 3. **Compound Word & Sandhi Support**
Handles Sanskrit compound words and word sandhi variations:
- **विष्णुर्नारायणः** matches **विष्णुः नारायणः** (with/without spaces)
- Creates variants with and without spaces
- Replaces spaces with avagraha and vice versa

## Implementation

### Files Modified

1. **sdl_web/sanskrit_utils.py**
   - Core normalization functions
   - `normalize_sanskrit()`: Main normalization function
   - `normalize_visarga()`: Handles final consonant rules
   - `create_search_variants()`: Generates alternative search patterns
   - `match_sanskrit_words()`: Checks if two words match under linguistic rules

2. **sdl_web/sdl.py**
   - Imported `sanskrit_utils` module
   - Updated `smart_search()` function with `sanskrit_normalize` parameter
   - Updated `search_in_folder()` function to pass normalization flag
   - Updated `/search/local` route to accept `sanskrit_normalize` parameter
   - Updated `/search/local/stream` route for SSE streaming support

3. **sdl_web/templates/public/index.html**
   - Added "Sanskrit Linguistic Rules" toggle switch in search form
   - Visual indicator (ℹ️) with tooltip explaining the feature
   - Updated `searchLocal()` JavaScript function to include toggle state

## Usage

### For Website Users

1. Open the search page at `/search`
2. Under the Advanced Filters section, check the box: "Sanskrit Linguistic Rules (visarga, avagraha)"
3. Enter your search query
4. Results will now match equivalent Sanskrit word forms

### For Developers

```python
from sanskrit_utils import match_sanskrit_words, create_search_variants

# Check if two words match under linguistic rules
word1 = "रामः"
word2 = "रामो"
is_match = match_sanskrit_words(word1, word2, apply_rules=True)
# Returns: True

# Get all variants of a word
variants = create_search_variants("रामः", apply_rules=True)
# Returns: ['रामः', 'रामो', 'रामं', 'राम...', etc.]
```

In search functions:
```python
# Smart search with normalization
results = smart_search(text_content, query, sanskrit_normalize=True)
```

## Test Cases

All test cases pass successfully:

| Word 1 | Word 2 | Match |
|--------|--------|-------|
| रामः | रामो | ✓ |
| हरिः | हरिर् | ✓ |
| रामोऽस्ति | रामोस्ति | ✓ |

## API Parameters

### Search Routes

Both `/search/local` and `/search/local/stream` accept:

- **sanskrit_normalize** (boolean): Enable/disable Sanskrit linguistic normalization
  - Default: `false`
  - Usage: `?sanskrit_normalize=true`

Example:
```
GET /search/local/stream?text_query=रामः&sanskrit_normalize=true
```

## Grammar Rules Implemented

### Panini's Visarga Rules
- Final consonant marker (ः) transformations based on next sound
- Anusvara (ं) as alternative to sibilant/visarga
- Pausal forms (ो-ending) as variant of ः-ending

### Sandhi Variations
- Word boundary transitions (samhita)
- Avagraha usage for elision marking
- Consonant cluster handling with halant (्)

## Performance Considerations

- Normalization is applied to both query and text content
- Search variants are cached during normalization
- Multiple variants are generated to catch all equivalent forms

## Future Enhancements

- Support for other Devanagari scripts (Kannada, Telugu, Tamil transliterations)
- Advanced sandhi rules for complex compound words
- Configurable rule sets for different Sanskrit texts
- Integration with Sanskrit dictionaries for lemmatization

## References

- Panini's Ashtadhyayi (Sanskrit Grammar Rules)
- Classical Sanskrit phonetics and orthography
- Vedic Sanskrit conventions
