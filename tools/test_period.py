text1 = "Ms. Voss"
text2 = "Solution."
text3 = "immediately."

for text in [text1, text2, text3]:
    ends = text.endswith(".")
    words = len(text.split())
    print(f"{text:20s} | ends=.:{ends}, words={words}")
