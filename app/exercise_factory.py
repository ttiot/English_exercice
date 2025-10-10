import random
from dataclasses import dataclass
from typing import Dict, List


@dataclass
class ExercisePrompt:
    prompt: str
    answer: str
    category: str


NUMBER_WORDS = {
    0: "zero",
    1: "one",
    2: "two",
    3: "three",
    4: "four",
    5: "five",
    6: "six",
    7: "seven",
    8: "eight",
    9: "nine",
    10: "ten",
    11: "eleven",
    12: "twelve",
    13: "thirteen",
    14: "fourteen",
    15: "fifteen",
    16: "sixteen",
    17: "seventeen",
    18: "eighteen",
    19: "nineteen",
    20: "twenty",
    30: "thirty",
    40: "forty",
    50: "fifty",
    60: "sixty",
    70: "seventy",
    80: "eighty",
    90: "ninety",
    100: "one hundred",
}

BASIC_TRANSLATIONS: Dict[str, str] = {
    "bonjour": "hello",
    "au revoir": "goodbye",
    "s'il te plaît": "please",
    "merci": "thank you",
    "chat": "cat",
    "chien": "dog",
    "maison": "house",
    "école": "school",
    "livre": "book",
    "pomme": "apple",
    "manger": "to eat",
    "boire": "to drink",
}

SIMPLE_SENTENCES: Dict[str, str] = {
    "I am ten years old": "J'ai dix ans",
    "He likes football": "Il aime le football",
    "She has a red bike": "Elle a un vélo rouge",
    "We are friends": "Nous sommes amis",
    "They go to school": "Ils vont à l'école",
}


def _generate_number_word_exercise() -> ExercisePrompt:
    number = random.choice(list(range(0, 101, 1)))
    if number > 20 and number not in NUMBER_WORDS:
        tens, ones = divmod(number, 10)
        tens_word = NUMBER_WORDS[tens * 10]
        if ones:
            word = f"{tens_word}-{NUMBER_WORDS[ones]}"
        else:
            word = tens_word
    else:
        word = NUMBER_WORDS.get(number, str(number))
    return ExercisePrompt(
        prompt=f"Écris en anglais le nombre {number}.",
        answer=word,
        category="number_word",
    )


def _generate_word_number_exercise() -> ExercisePrompt:
    number = random.choice(list(NUMBER_WORDS.keys()))
    return ExercisePrompt(
        prompt=f"Écris en chiffres le nombre '{NUMBER_WORDS[number]}'.",
        answer=str(number),
        category="word_number",
    )


def _generate_translation_fr_en() -> ExercisePrompt:
    french, english = random.choice(list(BASIC_TRANSLATIONS.items()))
    return ExercisePrompt(
        prompt=f"Traduis en anglais : '{french}'.",
        answer=english,
        category="translate_fr_en",
    )


def _generate_translation_en_fr() -> ExercisePrompt:
    english, french = random.choice(list({v: k for k, v in BASIC_TRANSLATIONS.items()}.items()))
    return ExercisePrompt(
        prompt=f"Traduis en français : '{english}'.",
        answer=french,
        category="translate_en_fr",
    )


def _generate_sentence_translation() -> ExercisePrompt:
    english, french = random.choice(list(SIMPLE_SENTENCES.items()))
    if random.choice([True, False]):
        return ExercisePrompt(
            prompt=f"Traduis en français : '{english}'.",
            answer=french,
            category="sentence_en_fr",
        )
    return ExercisePrompt(
        prompt=f"Traduis en anglais : '{french}'.",
        answer=english,
        category="sentence_fr_en",
    )


DEFAULT_GENERATORS = [
    _generate_number_word_exercise,
    _generate_word_number_exercise,
    _generate_translation_fr_en,
    _generate_translation_en_fr,
    _generate_sentence_translation,
]


def generate_default_exercises(quantity: int = 20) -> List[ExercisePrompt]:
    exercises: List[ExercisePrompt] = []
    for _ in range(quantity):
        generator = random.choice(DEFAULT_GENERATORS)
        exercises.append(generator())
    return exercises
