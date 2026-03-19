import re
from collections import Counter, defaultdict


TOKEN_PATTERN = re.compile(r"[a-zA-Z]{3,}")


def tokenize(text):
    return TOKEN_PATTERN.findall((text or "").lower())


class FrequencyConditionClassifier:
    def __init__(self, label_token_scores, fallback_label="General review required"):
        self.label_token_scores = label_token_scores
        self.fallback_label = fallback_label

    def predict(self, texts):
        return [self._predict_one(text) for text in texts]

    def _predict_one(self, text):
        token_counts = Counter(tokenize(text))
        label_scores = {}

        for label, token_scores in self.label_token_scores.items():
            score = 0
            for token, count in token_counts.items():
                score += token_scores.get(token, 0) * count
            if score:
                label_scores[label] = score

        if not label_scores:
            return self.fallback_label

        return max(label_scores, key=label_scores.get)


def train_frequency_condition_classifier(samples, max_tokens_per_label=60):
    label_counts = Counter()
    label_token_counts = defaultdict(Counter)
    global_token_counts = Counter()

    for text, label in samples:
        tokens = tokenize(text)
        if not tokens or not label:
            continue

        label_counts[label] += 1
        label_token_counts[label].update(tokens)
        global_token_counts.update(tokens)

    label_token_scores = {}
    for label, token_counter in label_token_counts.items():
        scored_tokens = []
        for token, label_count in token_counter.items():
            score = label_count / max(1, global_token_counts[token])
            scored_tokens.append((token, score))

        scored_tokens.sort(key=lambda item: (-item[1], item[0]))
        label_token_scores[label] = {
            token: round(score, 5) for token, score in scored_tokens[:max_tokens_per_label]
        }

    fallback_label = label_counts.most_common(1)[0][0] if label_counts else "General review required"
    return FrequencyConditionClassifier(label_token_scores, fallback_label=fallback_label)
