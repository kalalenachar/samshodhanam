/**
 * Sanskrit Digital Library (Samshodhana Mandiram)
 * Centralized Multi-Script Transliterator & Varga Panchama Engine
 * Supports: Devanagari (sa), Kannada (ka), Telugu (te), Tamil (ta), English IAST (en)
 */
(function (global) {
    'use strict';

    const SCRIPTS = ['sa', 'ka', 'te', 'ta', 'en'];

    const SCRIPT_INFO = {
        sa: { code: 'sa', name: 'Devanagari', nativeName: 'संस्कृतम्', font: "'Sanskrit Text', 'Noto Serif Devanagari', 'Noto Sans Devanagari', serif" },
        ka: { code: 'ka', name: 'Kannada', nativeName: 'ಕನ್ನಡ', font: "'Noto Serif Kannada', 'Noto Sans Kannada', 'Noto Serif Devanagari', 'Noto Sans Devanagari', serif" },
        te: { code: 'te', name: 'Telugu', nativeName: 'తెలుగు', font: "'Noto Serif Telugu', 'Noto Sans Telugu', 'Noto Serif Devanagari', 'Noto Sans Devanagari', serif" },
        ta: { code: 'ta', name: 'Tamil', nativeName: 'தமிழ்', font: "'Noto Serif Tamil', 'Noto Sans Tamil', 'Noto Serif Devanagari', 'Noto Sans Devanagari', serif" },
        en: { code: 'en', name: 'English (IAST)', nativeName: 'IAST', font: "'Inter', sans-serif" }
    };

    // Phoneme alignment table [sa, ka, te, ta, en]
    const PHONEME_TABLE = [
        // Independent Vowels (0-13)
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
        // Dependent Vowel Signs (14-26)
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
        // Halant/Virama (27)
        ['्', '್', '్', '்', ''],
        // Anusvara, Visarga (28-29)
        ['ं', 'ಂ', 'ం', 'ம்', 'ṃ'],
        ['ः', 'ಃ', 'ః', 'ஃ', 'ḥ'],
        // ka-varga (30-34)
        ['क', 'ಕ', 'క', 'க', 'k'],
        ['ख', 'ಖ', 'ఖ', 'க²', 'kh'],
        ['ग', 'ಗ', 'గ', 'க³', 'g'],
        ['घ', 'ಘ', 'ఘ', 'க⁴', 'gh'],
        ['ङ', 'ಙ', 'ఙ', 'ங', 'ṅ'],
        // ca-varga (35-39)
        ['च', 'ಚ', 'చ', 'ச', 'c'],
        ['छ', 'ಛ', 'ఛ', 'ச²', 'ch'],
        ['ज', 'ಜ', 'జ', 'ஜ', 'j'],
        ['झ', 'ಝ', 'ఝ', 'ஜ²', 'jh'],
        ['ञ', 'ಞ', 'ఞ', 'ஞ', 'ñ'],
        // ṭa-varga (40-44)
        ['ट', 'ಟ', 'ట', 'ட', 'ṭ'],
        ['ठ', 'ಠ', 'ఠ', 'ட²', 'ṭh'],
        ['ड', 'ಡ', 'డ', 'ட³', 'ḍ'],
        ['ढ', 'ಢ', 'ఢ', 'ட⁴', 'ḍh'],
        ['ण', 'ಣ', 'ణ', 'ண', 'ṇ'],
        // ta-varga (45-49)
        ['त', 'ತ', 'త', 'த', 't'],
        ['थ', 'ಥ', 'థ', 'த²', 'th'],
        ['द', 'ದ', 'ద', 'த³', 'd'],
        ['ध', 'ಧ', 'ధ', 'த⁴', 'dh'],
        ['न', 'ನ', 'న', 'ந', 'n'],
        // pa-varga (50-54)
        ['प', 'ಪ', 'ప', 'ப', 'p'],
        ['फ', 'ಫ', 'ఫ', 'ப²', 'ph'],
        ['ब', 'ಬ', 'బ', 'ப³', 'b'],
        ['भ', 'ಭ', 'భ', 'ப⁴', 'bh'],
        ['म', 'ಮ', 'మ', 'ம', 'm'],
        // avarga / semi-vowels (55-58)
        ['य', 'ಯ', 'య', 'ய', 'y'],
        ['र', 'ರ', 'ర', 'ர', 'r'],
        ['ल', 'ಲ', 'ల', 'ல', 'l'],
        ['व', 'ವ', 'వ', 'வ', 'v'],
        // sibilants & ha (59-62)
        ['श', 'ಶ', 'శ', 'ஶ', 'ś'],
        ['ष', 'ಷ', 'ష', 'ஷ', 'ṣ'],
        ['स', 'ಸ', 'స', 'ஸ', 's'],
        ['ह', 'ಹ', 'హ', 'ஹ', 'h'],
        // special (63)
        ['ळ', 'ಳ', 'ళ', 'ள', 'ḷ'],
        // Numbers (64-73)
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
        // Short-e, short-o variants (74-77)
        ['ऎ', 'ಎ', 'ఎ', 'எ', 'e'],
        ['ॆ', 'ೆ', 'ె', 'ெ', 'e'],
        ['ऒ', 'ಒ', 'ఒ', 'ஒ', 'o'],
        ['ॊ', 'ೊ', 'ొ', 'ொ', 'o'],
        // Om (78)
        ['ॐ', 'ಓಂ', 'ఓం', 'ஓம்', 'oṃ'],
        // Avagraha (79)
        ['ऽ', 'ಽ', 'ఽ', 'ऽ', '\''],
        // Chandrabindu (80)
        ['ँ', 'ಁ', 'ఁ', 'ஂ', 'm̐'],
        // Danda & Double Danda (81-82)
        ['।', '।', '।', '।', '|'],
        ['॥', '॥', '॥', '॥', '||']
    ];

    // Build lookup maps
    const charToIdx = SCRIPTS.map(() => ({}));
    const idxToChar = SCRIPTS.map(() => ({}));

    PHONEME_TABLE.forEach((row, rowIdx) => {
        SCRIPTS.forEach((_, sIdx) => {
            const ch = row[sIdx];
            if (ch !== undefined && ch !== null && ch.length > 0) {
                if (charToIdx[sIdx][ch] === undefined) {
                    charToIdx[sIdx][ch] = rowIdx;
                }
                if (idxToChar[sIdx][rowIdx] === undefined) {
                    idxToChar[sIdx][rowIdx] = ch;
                }
            }
        });
    });

    // Aliases for alternate Unicode representations
    if (charToIdx[3]['ௐ'] === undefined) charToIdx[3]['ௐ'] = charToIdx[0]['ॐ'];
    if (charToIdx[3]['\''] === undefined) charToIdx[3]['\''] = charToIdx[0]['ऽ'];
    if (charToIdx[3]['’'] === undefined) charToIdx[3]['’'] = charToIdx[0]['ऽ'];
    if (charToIdx[3]['‘'] === undefined) charToIdx[3]['‘'] = charToIdx[0]['ऽ'];
    if (charToIdx[4]['’'] === undefined) charToIdx[4]['’'] = charToIdx[0]['ऽ'];
    if (charToIdx[4]['‘'] === undefined) charToIdx[4]['‘'] = charToIdx[0]['ऽ'];
    if (charToIdx[4]['.'] === undefined) charToIdx[4]['.'] = charToIdx[0]['।'];

    // Devanagari OCR, nukta, and extended vowel/sign aliases
    if (charToIdx[0]['क़'] === undefined) charToIdx[0]['क़'] = charToIdx[0]['क'];
    if (charToIdx[0]['ख़'] === undefined) charToIdx[0]['ख़'] = charToIdx[0]['ख'];
    if (charToIdx[0]['ग़'] === undefined) charToIdx[0]['ग़'] = charToIdx[0]['ग'];
    if (charToIdx[0]['ज़'] === undefined) charToIdx[0]['ज़'] = charToIdx[0]['ज'];
    if (charToIdx[0]['ड़'] === undefined) charToIdx[0]['ड़'] = charToIdx[0]['ड'];
    if (charToIdx[0]['ढ़'] === undefined) charToIdx[0]['ढ़'] = charToIdx[0]['ढ'];
    if (charToIdx[0]['फ़'] === undefined) charToIdx[0]['फ़'] = charToIdx[0]['फ'];
    if (charToIdx[0]['य़'] === undefined) charToIdx[0]['य़'] = charToIdx[0]['य'];
    if (charToIdx[0]['ऩ'] === undefined) charToIdx[0]['ऩ'] = charToIdx[0]['न'];
    if (charToIdx[0]['ऱ'] === undefined) charToIdx[0]['ऱ'] = charToIdx[0]['र'];
    if (charToIdx[0]['ऴ'] === undefined) charToIdx[0]['ऴ'] = charToIdx[0]['ळ'];
    if (charToIdx[0]['ऄ'] === undefined) charToIdx[0]['ऄ'] = charToIdx[0]['अ'];
    if (charToIdx[0]['ऍ'] === undefined) charToIdx[0]['ऍ'] = charToIdx[0]['ए'];
    if (charToIdx[0]['ॅ'] === undefined) charToIdx[0]['ॅ'] = charToIdx[0]['े'];
    if (charToIdx[0]['ऑ'] === undefined) charToIdx[0]['ऑ'] = charToIdx[0]['ओ'];
    if (charToIdx[0]['ॉ'] === undefined) charToIdx[0]['ॉ'] = charToIdx[0]['ो'];
    if (charToIdx[0]['ॲ'] === undefined) charToIdx[0]['ॲ'] = charToIdx[0]['अ'];
    if (charToIdx[0]['ऀ'] === undefined) charToIdx[0]['ऀ'] = charToIdx[0]['ँ'];
    if (charToIdx[0]['ॎ'] === undefined) charToIdx[0]['ॎ'] = charToIdx[0]['े'];
    if (charToIdx[0]['ॏ'] === undefined) charToIdx[0]['ॏ'] = charToIdx[0]['ौ'];
    if (charToIdx[0]['॰'] === undefined) charToIdx[0]['॰'] = charToIdx[0]['।'];

    // Tamil multi-char tokens
    const tamilMultiTokens = [];
    PHONEME_TABLE.forEach(row => {
        const ch = row[3]; // Tamil
        if (ch && ch.length > 1 && !tamilMultiTokens.includes(ch)) {
            tamilMultiTokens.push(ch);
        }
    });
    tamilMultiTokens.sort((a, b) => b.length - a.length);

    // IAST multi-char sequences
    const iastSeq = ['oṃ', 'm̐', '||', 'ā', 'ī', 'ū', 'ē', 'ō', 'ṛ', 'ṝ', 'ḷ', 'ḹ', 'ai', 'au', 'e', 'o', 'i', 'u', 'ṃ', 'ḥ', 'ṅ', 'ñ', 'ṭh', 'ḍh', 'ṭ', 'ḍ', 'ṇ', 'ś', 'ṣ', 'kh', 'gh', 'ch', 'jh', 'th', 'dh', 'ph', 'bh'];

    function getChar(sIdx, rIdx, fallback) {
        if (sIdx === -1 || rIdx === undefined) return fallback;
        const ch = idxToChar[sIdx][rIdx];
        return (ch !== undefined) ? ch : fallback;
    }

    // Vedic accents regex: Udatta (\u0951), Anudatta (\u0952), Vedic Extensions (\u1CD0-\u1CF9), Devanagari Extended (\uA8E0-\uA8F1)
    const isVedicAccent = (code) => (code === 0x0951 || code === 0x0952 || (code >= 0x1CD0 && code <= 0x1CF9) || (code >= 0xA8E0 && code <= 0xA8F1));

    // Base phonetic conversion
    function convertScript(text, fromScriptName, toScriptName) {
        if (!text || fromScriptName === toScriptName) return text;
        if (typeof text.normalize === 'function') {
            // Decompose first so combining nukta (\u093C) is detached, strip nukta, then re-compose
            text = text.normalize('NFD').replace(/\u093C/g, '').normalize('NFC');
        }
        const fromIdx = SCRIPTS.indexOf(fromScriptName);
        const toIdx = SCRIPTS.indexOf(toScriptName);
        if (fromIdx === -1 || toIdx === -1) return text;

        let result = '';
        let i = 0;

        // Helper for IAST row selection
        const findBestIastRow = (seq, lastWasConsonant) => {
            const matchingRows = [];
            PHONEME_TABLE.forEach((r, idx) => { if (r[4] === seq) matchingRows.push(idx); });
            if (matchingRows.length === 0) return -1;

            if (lastWasConsonant) {
                const isSign = (idx) => (idx >= 14 && idx <= 26) || idx === 75 || idx === 77;
                const sRows = matchingRows.filter(idx => isSign(idx));
                if (sRows.length > 0) return sRows.find(idx => idx >= 14 && idx <= 26) || sRows[0];
            }

            const consonants = matchingRows.filter(idx => idx >= 30 && idx <= 63);
            if (consonants.length > 0) return consonants[0];

            const indVowels = matchingRows.filter(idx => (idx >= 0 && idx <= 13) || idx === 74 || idx === 76);
            if (indVowels.length > 0) return indVowels.find(idx => idx >= 0 && idx <= 13) || indVowels[0];

            return matchingRows[0];
        };

        // IAST input
        if (fromScriptName === 'en') {
            let lastWasConsonant = false;
            while (i < text.length) {
                const code = text.charCodeAt(i);
                if (isVedicAccent(code)) {
                    if (toScriptName === 'ta' && result.length > 0 && /[²³⁴]$/.test(result)) {
                        const lastSup = result.slice(-1);
                        result = result.slice(0, -1) + text[i] + lastSup;
                    } else {
                        result += text[i];
                    }
                    i++;
                    continue;
                }

                let matched = false;
                for (const seq of iastSeq) {
                    if (text.slice(i).startsWith(seq)) {
                        const rowIdx = findBestIastRow(seq, lastWasConsonant);
                        if (rowIdx !== -1) {
                            if (toScriptName === 'en') {
                                result += PHONEME_TABLE[rowIdx][4];
                            } else {
                                const isSign = (idx) => (idx >= 14 && idx <= 26) || idx === 75 || idx === 77;
                                const isIndVowel = (idx) => (idx >= 0 && idx <= 13) || idx === 74 || idx === 76;

                                if (isSign(rowIdx)) {
                                    result += getChar(toIdx, rowIdx, seq);
                                    lastWasConsonant = false;
                                } else if (isIndVowel(rowIdx)) {
                                    if (lastWasConsonant && rowIdx >= 1) {
                                        let signRowIdx = rowIdx + 13;
                                        if (rowIdx === 74) signRowIdx = 75;
                                        if (rowIdx === 76) signRowIdx = 77;
                                        result += getChar(toIdx, signRowIdx, getChar(toIdx, rowIdx, seq));
                                    } else {
                                        result += getChar(toIdx, rowIdx, seq);
                                    }
                                    lastWasConsonant = false;
                                } else {
                                    if (lastWasConsonant && rowIdx !== 28 && rowIdx !== 29) result += getChar(toIdx, 27, "");
                                    result += getChar(toIdx, rowIdx, seq);
                                    lastWasConsonant = (rowIdx >= 30 && rowIdx <= 63);
                                }
                            }
                            i += seq.length; matched = true; break;
                        }
                    }
                }
                if (!matched) {
                    const ch = text[i];
                    if (ch === 'a') {
                        if (!lastWasConsonant) result += getChar(toIdx, 0, 'अ');
                        lastWasConsonant = false;
                        i++; continue;
                    }

                    const rowIdx = findBestIastRow(ch, lastWasConsonant);
                    if (rowIdx !== -1) {
                        if (toScriptName === 'en') {
                            result += PHONEME_TABLE[rowIdx][4];
                        } else {
                            if (lastWasConsonant && rowIdx !== 28 && rowIdx !== 29) result += getChar(toIdx, 27, "");
                            result += getChar(toIdx, rowIdx, ch);
                            lastWasConsonant = (rowIdx >= 30 && rowIdx <= 63);
                        }
                    } else {
                        if (lastWasConsonant) result += getChar(toIdx, 27, "");
                        result += ch;
                        lastWasConsonant = false;
                    }
                    i++;
                }
            }
            if (lastWasConsonant && toScriptName !== 'en') result += getChar(toIdx, 27, "");
            return result;
        }

        // Brahmic scripts input (Devanagari, Kannada, Telugu, Tamil)
        const isTamil = fromScriptName === 'ta';

        while (i < text.length) {
            const code = text.charCodeAt(i);
            // Preserve Vedic accents directly (insert before Tamil superscripts to prevent dotted-circle breakage)
            if (isVedicAccent(code)) {
                if (toScriptName === 'ta' && result.length > 0 && /[²³⁴]$/.test(result)) {
                    const lastSup = result.slice(-1);
                    result = result.slice(0, -1) + text[i] + lastSup;
                } else {
                    result += text[i];
                }
                i++;
                continue;
            }

            let matched = false;

            // Tamil multi-tokens
            if (isTamil) {
                for (const tok of tamilMultiTokens) {
                    if (text.slice(i).startsWith(tok)) {
                        const rowIdx = charToIdx[3][tok];
                        if (rowIdx !== undefined) {
                            let out = (toScriptName === 'en') ? PHONEME_TABLE[rowIdx][4] : getChar(toIdx, rowIdx, tok);
                            result += out;
                            if (toScriptName === 'en' && rowIdx >= 30 && rowIdx <= 63) {
                                let isFollowedByVowel = false;
                                const nextRowIdx = charToIdx[fromIdx][text[i + tok.length]];
                                if (nextRowIdx !== undefined && ((nextRowIdx >= 14 && nextRowIdx <= 27) || nextRowIdx === 75 || nextRowIdx === 77)) isFollowedByVowel = true;
                                if (!isFollowedByVowel) result += 'a';
                            }
                            i += tok.length; matched = true; break;
                        }
                    }
                }
            }

            if (matched) continue;

            const ch = text[i];
            const nextCh = i + 1 < text.length ? text[i + 1] : '';
            const nextNextCh = i + 2 < text.length ? text[i + 2] : '';

            // Handle Tamil superscript after vowel sign/halant/accents: e.g. த + ே + ॒ + ³ -> de॒
            if (isTamil) {
                const rowIdx = charToIdx[fromIdx][ch];
                const isConsonant = rowIdx >= 30 && rowIdx <= 63;
                if (isConsonant) {
                    let j = i + 1;
                    let vowelSign = null;
                    let vowelRowIdx = null;
                    let superscript = null;
                    const accents = [];

                    while (j < text.length) {
                        const nextCode = text.charCodeAt(j);
                        const nextChar = text[j];
                        if (!superscript && /[²³⁴]/.test(nextChar)) {
                            superscript = nextChar;
                            j++;
                            continue;
                        }
                        if (isVedicAccent(nextCode)) {
                            accents.push(nextChar);
                            j++;
                            continue;
                        }
                        if (vowelSign === null && superscript === null) {
                            const nRowIdx = charToIdx[fromIdx][nextChar];
                            if (nRowIdx !== undefined && ((nRowIdx >= 14 && nRowIdx <= 27) || nRowIdx === 75 || nRowIdx === 77)) {
                                vowelSign = nextChar;
                                vowelRowIdx = nRowIdx;
                                j++;
                                continue;
                            }
                        }
                        break;
                    }

                    if (superscript) {
                        const baseChar = ch + superscript;
                        const baseRowIdx = charToIdx[fromIdx][baseChar];
                        if (baseRowIdx !== undefined) {
                            let out = (toScriptName === 'en') ? PHONEME_TABLE[baseRowIdx][4] : getChar(toIdx, baseRowIdx, baseChar);
                            result += out;
                            if (toScriptName === 'en') {
                                if (vowelRowIdx !== null && ((vowelRowIdx >= 14 && vowelRowIdx <= 26) || vowelRowIdx === 75 || vowelRowIdx === 77)) {
                                    result += PHONEME_TABLE[vowelRowIdx][4];
                                } else if (vowelRowIdx === null) {
                                    result += 'a';
                                }
                            } else {
                                if (vowelRowIdx !== null) {
                                    result += getChar(toIdx, vowelRowIdx, vowelSign);
                                }
                            }
                            if (accents.length > 0) {
                                result += accents.join('');
                            }
                            i = j;
                            continue;
                        }
                    }
                }
            }

            // Special handling for Tamil superscripts (OUTPUT to Tamil)
            if (toScriptName === 'ta' && result.length > 0) {
                const lastChar = result.slice(-1);
                if (/[²³⁴]/.test(lastChar)) {
                    const rowIdx = charToIdx[fromIdx][ch];
                    const isVowelOrHalant = (rowIdx >= 14 && rowIdx <= 27) || rowIdx === 75 || rowIdx === 77;
                    if (isVowelOrHalant) {
                        const superscript = lastChar;
                        const outVowel = getChar(toIdx, rowIdx, ch);
                        let preSupIdx = result.length - 1;
                        while (preSupIdx > 0 && isVedicAccent(result.charCodeAt(preSupIdx - 1))) {
                            preSupIdx--;
                        }
                        const accents = result.slice(preSupIdx, -1);
                        const base = result.slice(0, preSupIdx);
                        result = base + outVowel + accents + superscript;
                        i++; continue;
                    }
                }
            }

            const rowIdx = charToIdx[fromIdx][ch];
            if (rowIdx !== undefined) {
                let out = (toScriptName === 'en') ? PHONEME_TABLE[rowIdx][4] : getChar(toIdx, rowIdx, ch);
                result += out;
                // Implicit 'a' for consonants in English output
                if (toScriptName === 'en' && rowIdx >= 30 && rowIdx <= 63) {
                    const nextRowIdx = i + 1 < text.length ? charToIdx[fromIdx][text[i + 1]] : undefined;
                    const isSignOrHalant = nextRowIdx !== undefined && ((nextRowIdx >= 14 && nextRowIdx <= 27) || nextRowIdx === 75 || nextRowIdx === 77);
                    if (!isSignOrHalant) result += 'a';
                }
            } else {
                result += ch;
            }
            i++;
        }
        return result;
    }

    /**
     * Language-Specific Varga Panchama Rules:
     * - Kannada (ka): Internal nasals before varga consonants use anusvara (bindu / sonne ಂ).
     * - Telugu (te): Internal nasals before varga consonants use anusvara (sunna ం).
     * - Tamil (ta): Uses explicit class nasals (ங், ஞ், ண், ந், ம்).
     */
    function applyLanguageVargaPanchama(text, targetScript) {
        if (!text) return text;

        if (targetScript === 'ka') {
            // Convert class nasals + halant before varga consonants into anusvara (ಂ)
            // ka-varga: ಙ್ + (ಕ, ಖ, ಗ, ಘ) -> ಂ + (ಕ, ಖ, ಗ, ಘ)
            // ca-varga: ಞ್ + (ಚ, ಛ, ಜ, ಝ) -> ಂ + (ಚ, ಛ, ಜ, ಝ)
            // ṭa-varga: ಣ್ + (ಟ, ಠ, ಡ, ಢ) -> ಂ + (ಟ, ಠ, ಡ, ಢ)
            // ta-varga: ನ್ + (ತ, ಥ, ದ, ಧ) -> ಂ + (ತ, ಥ, ದ, ಧ)
            // pa-varga: ಮ್ + (ಪ, ಫ, ಬ, ಭ) -> ಂ + (ಪ, ಫ, ಬ, ಭ)
            return text
                .replace(/ಙ್(?=[ಕಖಗಘ])/g, 'ಂ')
                .replace(/ಞ್(?=[ಚಛಜಝ])/g, 'ಂ')
                .replace(/ಣ್(?=[ಟಠಡಢ])/g, 'ಂ')
                .replace(/ನ್(?=[ತಥದಧ])/g, 'ಂ')
                .replace(/ಮ್(?=[ಪಫಬಭ])/g, 'ಂ');
        }

        if (targetScript === 'te') {
            // Convert class nasals + halant before varga consonants into anusvara (ం)
            return text
                .replace(/ఙ్(?=[కఖగఘ])/g, 'ం')
                .replace(/ఞ్(?=[చఛజఝ])/g, 'ం')
                .replace(/ణ్(?=[టఠడఢ])/g, 'ం')
                .replace(/న్(?=[తథదధ])/g, 'ం')
                .replace(/మ్(?=[పఫబభ])/g, 'ం');
        }

        if (targetScript === 'ta') {
            // In Tamil, anusvara (represented in phonetic output as ம் or ம்் before consonants)
            // or explicit anusvara followed by varga consonants is converted to class nasals:
            // ka-varga (க, க², க³, க⁴) -> ங்
            // ca-varga (ச, ச², ஜ, ஜ²) -> ஞ்
            // ṭa-varga (ட, ட², ட³, ட⁴) -> ண்
            // ta-varga (த, த², த³, த⁴) -> ந்
            // pa-varga (ப, ப², ப³, ப⁴) -> ம்
            return text
                .replace(/ம்(?=க[²³⁴]?)/g, 'ங்')
                .replace(/ம்(?=[சஜ][²³⁴]?)/g, 'ஞ்')
                .replace(/ம்(?=ட[²³⁴]?)/g, 'ண்')
                .replace(/ம்(?=த[²³⁴]?)/g, 'ந்')
                .replace(/ம்(?=ப[²³⁴]?)/g, 'ம்');
        }

        return text;
    }

    /**
     * Automatically detect the script of a string
     * @param {string} text
     * @returns {'sa'|'ka'|'te'|'ta'|'en'}
     */
    function detectScript(text) {
        if (!text || typeof text !== 'string') return 'sa';
        let sa = 0, ka = 0, te = 0, ta = 0;
        for (let i = 0; i < text.length; i++) {
            const cp = text.charCodeAt(i);
            if (cp >= 0x0900 && cp <= 0x097F) sa++;
            else if (cp >= 0x0C80 && cp <= 0x0CFF) ka++;
            else if (cp >= 0x0C00 && cp <= 0x0C7F) te++;
            else if (cp >= 0x0B80 && cp <= 0x0BFF) ta++;
        }
        const maxCount = Math.max(sa, ka, te, ta);
        if (maxCount > 0) {
            if (maxCount === sa) return 'sa';
            if (maxCount === ka) return 'ka';
            if (maxCount === te) return 'te';
            if (maxCount === ta) return 'ta';
        }
        if (/[āīūṛṝḷḹēōṃḥṅñṭḍṇśṣ]/.test(text)) return 'en';
        return 'sa';
    }

    const SCRIPT_RANGES = {
        sa: [0x0900, 0x097F],
        ka: [0x0C80, 0x0CFF],
        te: [0x0C00, 0x0C7F],
        ta: [0x0B80, 0x0BFF]
    };

    /**
     * Detects if an unmapped letter or foreign script leakage exists in the converted output
     */
    function isScriptMismatch(origWord, convertedWord, fromScript, toScript) {
        if (toScript === fromScript) return false;

        // 1. Did source script characters leak through into convertedWord?
        if (SCRIPT_RANGES[fromScript] && toScript !== fromScript) {
            const [start, end] = SCRIPT_RANGES[fromScript];
            for (let i = 0; i < convertedWord.length; i++) {
                const cp = convertedWord.charCodeAt(i);
                if (isVedicAccent(cp)) continue;
                if (cp === 0x0964 || cp === 0x0965 || cp === 0x093D) continue; // Dandas & Avagraha are shared across Indian scripts
                if (cp >= start && cp <= end) {
                    return true;
                }
            }
        }

        // 2. If toScript is Indic, did characters from another foreign Indic script leak through?
        if (SCRIPT_RANGES[toScript]) {
            for (const s in SCRIPT_RANGES) {
                if (s !== toScript) {
                    const [oStart, oEnd] = SCRIPT_RANGES[s];
                    for (let i = 0; i < convertedWord.length; i++) {
                        const cp = convertedWord.charCodeAt(i);
                        if (isVedicAccent(cp)) continue;
                        if (cp === 0x0964 || cp === 0x0965 || cp === 0x093D) continue;
                        if (cp >= oStart && cp <= oEnd) {
                            return true;
                        }
                    }
                }
            }
        }

        return false;
    }

    /**
     * Transliterates a single word with unmapped letter detection and fallback bracket wrapping
     */
    function convertWordWithFallback(word, fromScript, toScript) {
        if (!word) return '';

        const hasIndic = /[\u0900-\u097F\u0C80-\u0CFF\u0C00-\u0C7F\u0B80-\u0BFF]/.test(word);

        // Base phonetic conversion
        let converted = convertScript(word, fromScript, toScript);

        // Language-specific Varga Panchama
        converted = applyLanguageVargaPanchama(converted, toScript);

        // Only wrap in brackets if target is English/IAST and unmapped characters leaked through.
        // For Indic-to-Indic (e.g. Devanagari to Tamil), returning raw foreign script inside brackets
        // breaks reader fonts and turns words into square boxes (tofu).
        if (toScript === 'en' && hasIndic && isScriptMismatch(word, converted, fromScript, toScript)) {
            return `(${word})`;
        }

        return converted;
    }

    /**
     * Main API: transliterateText
     * @param {string} text - Source text
     * @param {string} toScript - 'sa'|'ka'|'te'|'ta'|'en'
     * @param {string} [fromScript='auto'] - Source script (defaults to auto-detect)
     */
    function transliterateText(text, toScript, fromScript = 'auto') {
        if (!text) return '';
        if (!fromScript || fromScript === 'auto') {
            fromScript = detectScript(text);
        }
        if (fromScript === toScript) return text;

        // Split text into tokens (words and delimiters/whitespace/punctuation)
        const tokens = text.split(/([^\S\r\n]+|[।॥\s,;:!?"'()[\]{}<>\/\\–—\-]+)/);
        let output = '';

        for (let t = 0; t < tokens.length; t++) {
            const token = tokens[t];
            if (!token) continue;

            // If token is just whitespace or punctuation
            if (/^[।॥\s,;:!?"'()[\]{}<>\/\\–—\-]+$/.test(token)) {
                output += convertScript(token, fromScript, toScript);
                continue;
            }

            // Word token: transliterate with fallback
            output += convertWordWithFallback(token, fromScript, toScript);
        }

        return output;
    }

    /**
     * Recursively transliterates all text nodes inside a DOM element without destroying tags or events.
     * Caches the original text on node._smsdlOrigText so switching back and forth is 100% lossless.
     */
    function transliterateElement(rootEl, toScript, fromScript = 'auto') {
        if (!rootEl) return;

        const walker = document.createTreeWalker(
            rootEl,
            NodeFilter.SHOW_TEXT,
            {
                acceptNode: function (node) {
                    if (!node.nodeValue || !node.nodeValue.trim()) return NodeFilter.FILTER_SKIP;
                    const parent = node.parentElement;
                    if (!parent) return NodeFilter.FILTER_ACCEPT;
                    const tag = parent.tagName.toLowerCase();
                    if (tag === 'script' || tag === 'style' || tag === 'noscript' || tag === 'svg' || tag === 'code') {
                        return NodeFilter.FILTER_REJECT;
                    }
                    if (parent.classList.contains('no-transliterate') || parent.closest('.no-transliterate')) {
                        return NodeFilter.FILTER_REJECT;
                    }
                    return NodeFilter.FILTER_ACCEPT;
                }
            }
        );

        const nodes = [];
        let currentNode;
        while ((currentNode = walker.nextNode())) {
            nodes.push(currentNode);
        }

        nodes.forEach(node => {
            if (node._smsdlOrigText === undefined) {
                node._smsdlOrigText = node.nodeValue;
                node._smsdlSourceScript = detectScript(node.nodeValue);
            }
            const orig = node._smsdlOrigText;
            const srcScript = (fromScript && fromScript !== 'auto') ? fromScript : (node._smsdlSourceScript || 'sa');
            if (toScript === srcScript) {
                node.nodeValue = orig;
            } else {
                node.nodeValue = transliterateText(orig, toScript, srcScript);
            }
        });

        // Set font family attribute on container if appropriate
        if (toScript === 'ka') {
            rootEl.setAttribute('data-script-font', 'kannada');
        } else if (toScript === 'ta') {
            rootEl.setAttribute('data-script-font', 'tamil');
        } else if (toScript === 'te') {
            rootEl.setAttribute('data-script-font', 'telugu');
        } else if (toScript === 'sa') {
            rootEl.setAttribute('data-script-font', 'devanagari');
        } else {
            rootEl.removeAttribute('data-script-font');
        }

        const fontSetting = SCRIPT_INFO[toScript] ? SCRIPT_INFO[toScript].font : null;
        if (fontSetting && toScript !== 'sa') {
            rootEl.style.setProperty('font-family', fontSetting, 'important');
        } else {
            rootEl.style.removeProperty('font-family');
        }
    }

    /**
     * Get plain text version of element's content transliterated into target script
     */
    function getTransliteratedContent(element, toScript, fromScript = 'sa') {
        if (!element) return '';
        // If element has data-original-raw, use that
        const raw = element.getAttribute('data-original-raw') || element.innerText || element.textContent || '';
        return transliterateText(raw, toScript, fromScript);
    }

    /**
     * Creates or updates the standardized Script Selector Popover UI
     */
    function setupScriptSelector({
        buttonId,
        popoverId,
        activeLabelId,
        storageKey,
        defaultScript = 'sa',
        onSelect
    }) {
        const savedScript = localStorage.getItem(storageKey) || defaultScript;

        function updateUI(script) {
            const info = SCRIPT_INFO[script] || SCRIPT_INFO.sa;
            const labelEl = document.getElementById(activeLabelId);
            if (labelEl) {
                labelEl.textContent = info.nativeName;
            }
            const popover = document.getElementById(popoverId);
            if (popover) {
                popover.querySelectorAll('.script-option-item').forEach(item => {
                    const itemScript = item.getAttribute('data-script');
                    if (itemScript === script) {
                        item.classList.add('active');
                        const chk = item.querySelector('.script-check');
                        if (chk) chk.style.display = 'inline';
                    } else {
                        item.classList.remove('active');
                        const chk = item.querySelector('.script-check');
                        if (chk) chk.style.display = 'none';
                    }
                });
            }
        }

        window.toggleScriptPickerPopover = function (event) {
            if (event) {
                event.stopPropagation();
                event.preventDefault();
            }
            const popover = document.getElementById(popoverId);
            if (!popover) return;
            const isVisible = popover.style.display === 'block';
            document.querySelectorAll('.script-picker-popover').forEach(p => {
                if (p.id !== popoverId) p.style.display = 'none';
            });
            popover.style.display = isVisible ? 'none' : 'block';
        };

        window.closeScriptPickerPopover = function () {
            const popover = document.getElementById(popoverId);
            if (popover) popover.style.display = 'none';
        };

        window.selectScript = function (scriptCode) {
            localStorage.setItem(storageKey, scriptCode);
            updateUI(scriptCode);
            closeScriptPickerPopover();
            if (typeof onSelect === 'function') {
                onSelect(scriptCode);
            }
        };

        document.addEventListener('click', function (e) {
            const btn = document.getElementById(buttonId);
            const pop = document.getElementById(popoverId);
            if (pop && pop.style.display === 'block') {
                if ((!btn || !btn.contains(e.target)) && !pop.contains(e.target)) {
                    pop.style.display = 'none';
                }
            }
        });

        updateUI(savedScript);
        return savedScript;
    }

    /**
     * Returns rich, formatted guide HTML for the specified script transliteration
     */
    function getScriptGuideHTML(scriptCode) {
        if (!scriptCode || scriptCode === 'sa') return '';
        if (scriptCode === 'ta') {
            return `
                <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 8px; padding-bottom: 6px; border-bottom: 1px solid rgba(255,255,255,0.1);">
                    <div style="font-weight: 700; color: #38bdf8; font-size: 13px; display: flex; align-items: center; gap: 6px;">
                        <span>🌐 தமிழ் (Tamil) Transliteration Guide</span>
                    </div>
                    <span style="font-size: 10px; background: rgba(56,189,248,0.2); color: #38bdf8; padding: 2px 7px; border-radius: 10px; font-weight: 600;">Active</span>
                </div>
                <div style="font-size: 12px; color: var(--t-text-secondary, #cbd5e1); display: flex; flex-direction: column; gap: 7px; line-height: 1.45;">
                    <div>
                        <strong style="color: var(--t-text-primary, #f8fafc);">• Superscripts (², ³, ⁴):</strong> Tamil script natively has only 1 consonant per row. Superscript numbers indicate voiced and aspirated sounds:
                        <div style="margin-top: 3px; padding: 5px 8px; background: rgba(0,0,0,0.3); border-radius: 6px; font-family: 'Noto Serif Tamil', serif; font-size: 11.5px; line-height: 1.4; color: #e0e7ff;">
                            <div>க (ka), க² (kha), க³ (ga), க⁴ (gha)</div>
                            <div>த (ta), த² (tha), த³ (da), த⁴ (dha)</div>
                            <div>ப (pa), ப² (pha), ப³ (ba), ப⁴ (bha)</div>
                        </div>
                    </div>
                    <div><strong style="color: var(--t-text-primary, #f8fafc);">• Avagraha (ऽ):</strong> Preserved directly as <strong style="color: #38bdf8; font-family: serif; font-size: 13px;">ऽ</strong> to clearly indicate Sanskrit vowel elision (<em>lopa</em>).</div>
                    <div><strong style="color: var(--t-text-primary, #f8fafc);">• Grantha Consonants:</strong> <strong>ஜ, ஷ, ஸ, ஹ, க்ஷ, ஶ்</strong> are used for precise Sanskrit sounds.</div>
                    <div><strong style="color: var(--t-text-primary, #f8fafc);">• Class Nasals:</strong> Proper Sanskrit varga nasals (ங், ஞ், ண், ந், ம்) are maintained.</div>
                </div>
                <div style="margin-top: 8px; padding-top: 6px; border-top: 1px solid rgba(255,255,255,0.08); font-size: 11px; color: var(--t-text-muted, #94a3b8); text-align: center;">
                    Switch back to original Sanskrit (Devanagari) anytime from the 🌐 Reading Script menu.
                </div>
            `;
        } else if (scriptCode === 'ka') {
            return `
                <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 8px; padding-bottom: 6px; border-bottom: 1px solid rgba(255,255,255,0.1);">
                    <div style="font-weight: 700; color: #38bdf8; font-size: 13px; display: flex; align-items: center; gap: 6px;">
                        <span>🌐 ಕನ್ನಡ (Kannada) Transliteration Guide</span>
                    </div>
                    <span style="font-size: 10px; background: rgba(56,189,248,0.2); color: #38bdf8; padding: 2px 7px; border-radius: 10px; font-weight: 600;">Active</span>
                </div>
                <div style="font-size: 12px; color: var(--t-text-secondary, #cbd5e1); display: flex; flex-direction: column; gap: 7px; line-height: 1.45;">
                    <div><strong style="color: var(--t-text-primary, #f8fafc);">• Full Alphabet:</strong> Complete 1-to-1 representation of all Sanskrit vowels, mahāprāṇas, and conjuncts.</div>
                    <div><strong style="color: var(--t-text-primary, #f8fafc);">• Bindu / Anusvara (ಂ):</strong> Internal Sanskrit nasals before varga consonants use anusvara (<em>sonne</em> ಂ).</div>
                    <div><strong style="color: var(--t-text-primary, #f8fafc);">• Avagraha (ಽ):</strong> Traditional Kannada avagraha represents Sanskrit vowel elision (<em>lopa</em>).</div>
                </div>
                <div style="margin-top: 8px; padding-top: 6px; border-top: 1px solid rgba(255,255,255,0.08); font-size: 11px; color: var(--t-text-muted, #94a3b8); text-align: center;">
                    Switch back to original Sanskrit (Devanagari) anytime from the 🌐 Reading Script menu.
                </div>
            `;
        } else if (scriptCode === 'te') {
            return `
                <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 8px; padding-bottom: 6px; border-bottom: 1px solid rgba(255,255,255,0.1);">
                    <div style="font-weight: 700; color: #38bdf8; font-size: 13px; display: flex; align-items: center; gap: 6px;">
                        <span>🌐 తెలుగు (Telugu) Transliteration Guide</span>
                    </div>
                    <span style="font-size: 10px; background: rgba(56,189,248,0.2); color: #38bdf8; padding: 2px 7px; border-radius: 10px; font-weight: 600;">Active</span>
                </div>
                <div style="font-size: 12px; color: var(--t-text-secondary, #cbd5e1); display: flex; flex-direction: column; gap: 7px; line-height: 1.45;">
                    <div><strong style="color: var(--t-text-primary, #f8fafc);">• Full Alphabet:</strong> Complete 1-to-1 representation of all Sanskrit vowels, mahāprāṇas, and conjuncts.</div>
                    <div><strong style="color: var(--t-text-primary, #f8fafc);">• Sunna / Anusvara (ం):</strong> Internal Sanskrit nasals before varga consonants use anusvara (<em>sunna</em> ం).</div>
                    <div><strong style="color: var(--t-text-primary, #f8fafc);">• Avagraha (ఽ):</strong> Traditional Telugu avagraha represents Sanskrit vowel elision (<em>lopa</em>).</div>
                </div>
                <div style="margin-top: 8px; padding-top: 6px; border-top: 1px solid rgba(255,255,255,0.08); font-size: 11px; color: var(--t-text-muted, #94a3b8); text-align: center;">
                    Switch back to original Sanskrit (Devanagari) anytime from the 🌐 Reading Script menu.
                </div>
            `;
        } else if (scriptCode === 'en') {
            return `
                <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 8px; padding-bottom: 6px; border-bottom: 1px solid rgba(255,255,255,0.1);">
                    <div style="font-weight: 700; color: #38bdf8; font-size: 13px; display: flex; align-items: center; gap: 6px;">
                        <span>🌐 English (IAST) Transliteration Guide</span>
                    </div>
                    <span style="font-size: 10px; background: rgba(56,189,248,0.2); color: #38bdf8; padding: 2px 7px; border-radius: 10px; font-weight: 600;">Active</span>
                </div>
                <div style="font-size: 12px; color: var(--t-text-secondary, #cbd5e1); display: flex; flex-direction: column; gap: 7px; line-height: 1.45;">
                    <div><strong style="color: var(--t-text-primary, #f8fafc);">• Standard Scholarly IAST:</strong> International Alphabet of Sanskrit Transliteration with diacritics.</div>
                    <div><strong style="color: var(--t-text-primary, #f8fafc);">• Long Vowels:</strong> Macrons (ā, ī, ū, ṝ, ḹ).</div>
                    <div><strong style="color: var(--t-text-primary, #f8fafc);">• Retroflexes:</strong> Underdots (ṭ, ṭh, ḍ, ḍh, ṇ, ṣ, ṛ).</div>
                    <div><strong style="color: var(--t-text-primary, #f8fafc);">• Special Marks:</strong> ṅ (velar), ñ (palatal), ś (palatal sibilant), ḥ (visarga), ṃ (anusvara), ' (avagraha).</div>
                </div>
                <div style="margin-top: 8px; padding-top: 6px; border-top: 1px solid rgba(255,255,255,0.08); font-size: 11px; color: var(--t-text-muted, #94a3b8); text-align: center;">
                    Switch back to original Sanskrit (Devanagari) anytime from the 🌐 Reading Script menu.
                </div>
            `;
        }
        return '';
    }

    // Export to global scope
    global.SamshoTranslit = {
        SCRIPTS,
        SCRIPT_INFO,
        PHONEME_TABLE,
        convertScript,
        applyLanguageVargaPanchama,
        transliterateText,
        transliterateElement,
        getTransliteratedContent,
        setupScriptSelector,
        detectScript,
        getScriptGuideHTML
    };

})(typeof window !== 'undefined' ? window : this);
