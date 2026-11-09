"""
Precomputed Top-K Trie & Inverted Index for Fast, Typo-Tolerant Search.
Combines O(L) prefix autocomplete with Levenshtein fuzzy matching and inverted indexing.
"""
from typing import Dict, List, Tuple, Any, Set, Optional

class AutocompleteTrie:
    def __init__(self, k: int = 5):
        self.root: Dict[str, Any] = {'c': {}, 'top': []}
        self.k = k

    def insert(self, query: str, score: int = 1) -> None:
        """Insert query and maintain top-k precomputed suggestions at each node."""
        clean = query.strip().lower()
        if not clean:
            return

        node = self.root
        self._update_top_k(node, clean, score)

        for char in clean:
            if char not in node['c']:
                node['c'][char] = {'c': {}, 'top': []}
            node = node['c'][char]
            self._update_top_k(node, clean, score)

    def _update_top_k(self, node: Dict[str, Any], query: str, score: int) -> None:
        """Keep top-k queries sorted by score descending."""
        entries = [e for e in node['top'] if e[0] != query]
        entries.append((query, score))
        entries.sort(key=lambda x: x[1], reverse=True)
        node['top'] = entries[:self.k]

    def search(self, prefix: str) -> List[str]:
        """O(len(prefix)) instant exact prefix lookup."""
        clean = prefix.strip().lower()
        if not clean:
            return [q for q, _ in self.root['top']]

        node = self.root
        for char in clean:
            if char not in node['c']:
                return []
            node = node['c'][char]
        return [q for q, _ in node['top']]

    def fuzzy_search(self, query: str, max_distance: int = 1) -> List[str]:
        """Typo-tolerant autocomplete using bounded Trie-Levenshtein traversal."""
        clean = query.strip().lower()
        if not clean:
            return self.search('')

        # Exact prefix match first
        exact = self.search(clean)
        if exact:
            return exact

        # Bounded fuzzy match across Trie nodes
        current_row = list(range(len(clean) + 1))
        results: Dict[str, Tuple[str, int]] = {}
        for char, child in self.root['c'].items():
            self._fuzzy_recurse(child, char, clean, current_row, results, max_distance)

        ranked = sorted(results.values(), key=lambda x: x[1], reverse=True)
        return [q for q, _ in ranked[:self.k]]

    def _fuzzy_recurse(self, node: Dict[str, Any], letter: str, word: str,
                       prev_row: List[int], results: Dict[str, Tuple[str, int]],
                       max_distance: int) -> None:
        columns = len(word) + 1
        curr_row = [prev_row[0] + 1]
        for col in range(1, columns):
            insert_cost = curr_row[col - 1] + 1
            delete_cost = prev_row[col] + 1
            replace_cost = prev_row[col - 1] if word[col - 1] == letter else prev_row[col - 1] + 1
            curr_row.append(min(insert_cost, delete_cost, replace_cost))

        if curr_row[-1] <= max_distance:
            for q, sc in node['top']:
                if q not in results or sc > results[q][1]:
                    results[q] = (q, sc)

        if min(curr_row) <= max_distance:
            for ch, child in node['c'].items():
                self._fuzzy_recurse(child, ch, word, curr_row, results, max_distance)

    def serialize(self) -> Dict[str, Any]:
        return {'k': self.k, 'root': self.root}

    @classmethod
    def deserialize(cls, data: Dict[str, Any]) -> "AutocompleteTrie":
        trie = cls(k=data.get('k', 5))
        trie.root = data.get('root', {'c': {}, 'top': []})
        return trie


class InvertedIndex:
    """Word-to-entity ID inverted index for fast keyword lookups without table scans."""
    def __init__(self):
        self.index: Dict[str, Set[str]] = {}

    def add(self, entity_id: str, text: str) -> None:
        tokens = text.lower().strip().split()
        for token in tokens:
            if len(token) > 1:
                self.index.setdefault(token, set()).add(entity_id)

    def lookup(self, query: str) -> Set[str]:
        tokens = query.lower().strip().split()
        if not tokens:
            return set()
        matched: Optional[Set[str]] = None
        for token in tokens:
            docs = self.index.get(token, set())
            matched = docs if matched is None else matched & docs
        return matched or set()
