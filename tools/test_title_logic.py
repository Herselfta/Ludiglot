text = "Ms. Voss"
word_count = len(text.split())
char_count = len(text)
stripped = text.rstrip()
ends_with_period = stripped.endswith('.')
has_sentence_punct = any(ch in text for ch in [',', '!', '?', ':'])
is_likely_sentence = has_sentence_punct or (ends_with_period and word_count == 1)
is_title = word_count <= 3 and char_count <= 30 and not is_likely_sentence

print(f'text="{text}"')
print(f'word_count={word_count}, char_count={char_count}')
print(f'stripped="{stripped}"')
print(f'ends_with_period={ends_with_period}')
print(f'has_sentence_punct={has_sentence_punct}')
print(f'is_likely_sentence={is_likely_sentence}')
print(f'is_title={is_title}')
