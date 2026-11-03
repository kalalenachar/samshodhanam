"""
Sanskrit NLP Engine Architecture
------------------------------
A centralized processor wrapper combining 5 state-of-the-art libraries:
1. chanda          : Meter and prosody classification.
2. vidyut.cheda    : Text segmentation using deep vocabulary filtering.
3. vidyut.kosha    : 100-million word lexicon dataset built from Paninian grammar.
4. sanskrit_parser : Structural dependency graph generation (Karaka mapping).
5. vidyut.prakriya : Step-by-step derivational rule engine based on the Ashtadhyayi.
6. sandhi          : Pure mathematical phonetic combiner.
"""

import os
import json
import logging
from typing import List, Dict, Any

# Sanskrit Comp-Ling Stack Imports
try:
    import chanda
    from vidyut.kosha import Kosha
    from vidyut.cheda import Chedaka
    from vidyut.prakriya import Vyakarana
    from sanskrit_parser import Parser
    from sanskrit_parser.api import ParseNode, ParseEdge
    from vidyut.lipi import Scheme, transliterate
    import sandhi
except ImportError:
    chanda = None
    Kosha = None
    Chedaka = None
    Vyakarana = None
    Parser = None
    ParseNode = None
    ParseEdge = None
    Scheme = None
    transliterate = None
    sandhi = None


class SanskritNLPProcessor:
    """
    Unified Sanskrit Processing Engine managing memory-heavy lexicon resources 
    and providing strict data passing across 5 computational layers.
    """
    
    def __init__(self, kosha_data_path: str):
        """
        Initializes the Sanskrit processing pipeline.
        
        :param kosha_data_path: Path to the compiled vidyut-kosha database files or root vidyut-data path.
        """
        # Resolve data_path and kosha_data_path
        if os.path.basename(kosha_data_path) == 'kosha':
            data_path = os.path.dirname(kosha_data_path)
        else:
            data_path = kosha_data_path
            kosha_data_path = os.path.join(data_path, 'kosha')

        if not os.path.exists(kosha_data_path):
            raise FileNotFoundError(
                f"Vidyut Kosha data directory not found at: {kosha_data_path}. "
                f"Please ensure you download the pre-compiled Paninian lexicon database."
            )
            
        print("Initializing Sanskrit NLP Stack components...")
        
        # 1. Initialize Lexicon Barrier Data (Loaded ONCE globally into RAM)
        if Kosha and os.path.exists(kosha_data_path):
            try:
                print(" -> Loading Paninian Lexicon database into memory (vidyut.kosha)...")
                self.kosha = Kosha(kosha_data_path)
            except Exception as e:
                print(f" -> Warning loading Kosha: {e}")
                self.kosha = None
        else:
            self.kosha = None
        
        # 2. Bind Lexicon to Segmenter (Chedaka)
        if Chedaka and os.path.exists(data_path):
            try:
                print(" -> Instantiating Chedaka Segmenter (vidyut.cheda)...")
                self.cheda = Chedaka(data_path)
            except Exception as e:
                print(f" -> Warning loading Chedaka: {e}")
                self.cheda = None
        else:
            self.cheda = None
        
        # 3. Instantiate the Dependency Syntax Graph engine
        if Parser:
            try:
                print(" -> Initializing Syntax Engine (sanskrit_parser)...")
                self.syntax_parser = Parser()
            except Exception as e:
                print(f" -> Warning loading Parser: {e}")
                self.syntax_parser = None
        else:
            self.syntax_parser = None
        
        # 4. Instantiate the Ashtadhyayi Rule Engine (Vyakarana)
        if Vyakarana:
            try:
                print(" -> Loading Ashtadhyayi Prakriya System (vidyut.prakriya)...")
                self.prakriya = Vyakarana()
            except Exception as e:
                print(f" -> Warning loading Vyakarana: {e}")
                self.prakriya = None
        else:
            self.prakriya = None
        
        print("Sanskrit NLP Stack initialization complete.")

    def analyze_verse(self, raw_verse: str) -> Dict[str, Any]:
        """
        Workflow A: Deep Linguistic Profiling
        Parses a continuous raw string or verse layout into its exact
        prosodic, semantic, syntactic, and morphological primitives.
        
        :param raw_verse: Continuous Sanskrit input string in Devanagari.
        :return: Structured Dictionary containing the distinct linguistic profiles.
        """
        profile = {
            "prosody": {},
            "segmentation": [],
            "syntax": {},
            "morphology": {}
        }
        
        # --- Layer 1: Prosody & Meter Analysis (chanda) ---
        try:
            meter_result = chanda.analyze_line(raw_verse, fuzzy=True)
            chanda_list = getattr(meter_result, 'chanda', [])
            profile["prosody"] = {
                "meter_name": chanda_list[0][0] if chanda_list else 'Unknown/Muktaka',
                "laghu_guru_pattern": "".join(getattr(meter_result, 'lg', [])),
                "gana_sequence": getattr(meter_result, 'gana', ''),
                "is_fuzzy_matched": len(getattr(meter_result, 'fuzzy', [])) > 0
            }
        except Exception as e:
            profile["prosody"] = {"error": f"Chanda Analysis Failed: {str(e)}"}

        # --- Layer 2: Lexical Segmentation (vidyut.cheda) ---
        try:
            # Transliterate to SLP1 for Chedaka
            slp1_text = transliterate(raw_verse, Scheme.Devanagari, Scheme.Slp1)
            cheda_result = self.cheda.run(slp1_text)
            segmented_words = [transliterate(t.text, Scheme.Slp1, Scheme.Devanagari) for t in cheda_result]
            profile["segmentation"] = segmented_words
        except Exception as e:
            profile["segmentation"] = {"error": f"Segmentation Failed: {str(e)}"}
            return profile # Early return as subsequent layers rely on successful tokens

        # --- Layer 3: Syntax & Karaka Dependency (sanskrit_parser) ---
        segmented_list = profile["segmentation"]
        try:
            # Suppress verbose sanskrit_parser logger
            logging.getLogger('sanskrit_parser').setLevel(logging.WARNING)
            
            # Parse syntax tree
            splits = list(self.syntax_parser.split(" ".join(segmented_list), pre_segmented=True))
            if splits:
                parses = list(splits[0].parse(limit=1))
                if parses:
                    parse = parses[0]
                    verbs = []
                    subjects = []
                    objects = []
                    relations = []
                    
                    for item in parse.graph:
                        if isinstance(item, ParseNode):
                            tags = item.parse_tag.tags if hasattr(item, 'parse_tag') and hasattr(item.parse_tag, 'tags') else []
                            is_verb = any(t in ['law', 'liw', 'luw', 'lfw', 'low', 'laN', 'vidhiliN', 'ASIrliN', 'luN', 'lrN'] for t in tags)
                            if is_verb:
                                verbs.append(str(item.pada))
                        else:
                            # ParseEdge
                            relations.append({
                                "source": str(item.predecessor.pada),
                                "target": str(item.node.pada),
                                "relation": item.label
                            })
                            if 'kart' in item.label.lower():
                                subjects.append(str(item.node.pada))
                            elif 'karm' in item.label.lower():
                                objects.append(str(item.node.pada))
                    
                    # Convert to Devanagari for readability
                    dev_verbs = [transliterate(v, Scheme.Slp1, Scheme.Devanagari) for v in verbs]
                    dev_subjects = [transliterate(s, Scheme.Slp1, Scheme.Devanagari) for s in subjects]
                    dev_objects = [transliterate(o, Scheme.Slp1, Scheme.Devanagari) for o in objects]
                    dev_relations = []
                    for r in relations:
                        dev_relations.append({
                            "source": transliterate(r["source"], Scheme.Slp1, Scheme.Devanagari),
                            "target": transliterate(r["target"], Scheme.Slp1, Scheme.Devanagari),
                            "relation": r["relation"]
                        })

                    profile["syntax"] = {
                        "relations": dev_relations, 
                        "subject_tokens": dev_subjects, # Kartā
                        "object_tokens": dev_objects,   # Karma
                        "verb_tokens": dev_verbs        # Kriyā
                    }
                else:
                    profile["syntax"] = {"error": "No valid parse graph generated"}
            else:
                profile["syntax"] = {"error": "Syntactic parsing failed to split"}
        except Exception as e:
            profile["syntax"] = {"error": f"Syntactic Analysis Failed: {str(e)}"}

        # --- Layer 4: Morphological Ashtadhyayi Derivation (vidyut.prakriya) ---
        try:
            verbs = profile["syntax"].get("verb_tokens", [])
            if verbs:
                primary_verb = verbs[0]
                slp1_verb = transliterate(primary_verb, Scheme.Devanagari, Scheme.Slp1)
                entries = self.kosha.get(slp1_verb)
                
                # Try to locate a verbal entry
                verbal_entry = None
                for entry in entries:
                    if 'Tinanta' in str(type(entry)):
                        verbal_entry = entry
                        break
                if not verbal_entry and entries:
                    verbal_entry = entries[0]
                
                if verbal_entry:
                    derivations = self.prakriya.derive(verbal_entry)
                    if derivations:
                        best_derivation = derivations[0]
                        profile["morphology"] = {
                            "target_word": primary_verb,
                            "dhatu_root": transliterate(best_derivation.dhatu.aupadeshika, Scheme.Slp1, Scheme.Devanagari) if hasattr(best_derivation.dhatu, 'aupadeshika') else best_derivation.dhatu.text,
                            "pratyaya_affixes": [transliterate(p.text, Scheme.Slp1, Scheme.Devanagari) for p in best_derivation.pratyayas] if hasattr(best_derivation, 'pratyayas') else [],
                            "paninian_sutra_steps": [step.code for step in best_derivation.history]
                        }
        except Exception as e:
            profile["morphology"] = {"error": f"Morphological Derivation Failed: {str(e)}"}

        return profile

    def combine_words(self, word_list: List[str]) -> str:
        """
        Workflow B: Generative Sentence Formatting
        Converts a collection of separate words into a fluent text segment
        by applying deterministic phonetic merging rules.
        
        :param word_list: An ordered sequence of isolated Sanskrit Padas.
        :return: A single, sandhi-fused continuous string.
        """
        if not word_list:
            return ""
            
        try:
            s = sandhi.Sandhi()
            current = word_list[0]
            for next_word in word_list[1:]:
                res = s.sandhi(current, next_word)
                if res:
                    current = res[0][0]
                else:
                    current = current + " " + next_word
            return current
        except Exception as e:
            # Fallback to simple space separation if unexpected sound laws break execution
            print(f"Warning: Sandhi combining encountered standard execution error: {str(e)}")
            return " ".join(word_list)


# Self-contained testing configuration block
if __name__ == "__main__":
    print("Sanskrit NLP Processor script executed directly. Ready for programmatic imports.")