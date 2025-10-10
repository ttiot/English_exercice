import random
from dataclasses import dataclass
from typing import Callable, Dict, Iterable, List, Optional, Sequence, Tuple


@dataclass(frozen=True)
class ExercisePrompt:
    prompt: str
    answer: str
    category: str


@dataclass(frozen=True)
class GeneratorSpec:
    difficulties: Sequence[str]
    builder: Callable[[str], ExercisePrompt]


DIFFICULTY_LEVELS: Tuple[str, ...] = ("beginner", "intermediate", "advanced")
DIFFICULTY_LABELS: Dict[str, str] = {
    "beginner": "Débutant",
    "intermediate": "Intermédiaire",
    "advanced": "Avancé",
}

UNITS_AND_TEENS: Dict[int, str] = {
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
}

TENS_WORDS: Dict[int, str] = {
    20: "twenty",
    30: "thirty",
    40: "forty",
    50: "fifty",
    60: "sixty",
    70: "seventy",
    80: "eighty",
    90: "ninety",
}

HOUR_WORDS: Dict[int, str] = {
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
}

FR_EN_TRANSLATIONS: Dict[str, Dict[str, str]] = {
    "beginner": {
        "bonjour": "hello",
        "au revoir": "goodbye",
        "s'il te plaît": "please",
        "merci": "thank you",
        "pomme": "apple",
        "chat": "cat",
        "chien": "dog",
        "maison": "house",
        "stylo": "pen",
        "cahier": "notebook",
        "ami": "friend",
        "école": "school",
    },
    "intermediate": {
        "bibliothèque": "library",
        "devoirs": "homework",
        "terrain de jeu": "playground",
        "trousse": "pencil case",
        "cartable": "schoolbag",
        "stylo plume": "fountain pen",
        "été": "summer",
        "hiver": "winter",
    },
    "advanced": {
        "progrès": "progress",
        "environnement": "environment",
        "tradition": "tradition",
        "sciences": "science",
        "projet": "project",
        "imagination": "imagination",
    },
}

SENTENCE_BANK: Dict[str, List[Tuple[str, str]]] = {
    "beginner": [
        ("I have a blue backpack.", "J'ai un sac à dos bleu."),
        ("He likes football.", "Il aime le football."),
        ("We are in the classroom.", "Nous sommes dans la classe."),
        ("They are best friends.", "Ils sont meilleurs amis."),
    ],
    "intermediate": [
        ("She plays the piano every Tuesday.", "Elle joue du piano chaque mardi."),
        ("My parents work in the city.", "Mes parents travaillent en ville."),
        ("The lesson starts at nine o'clock.", "Le cours commence à neuf heures."),
        ("We eat lunch at the cafeteria.", "Nous déjeunons à la cantine."),
    ],
    "advanced": [
        ("They are preparing a project about English-speaking countries.", "Ils préparent un projet sur les pays anglophones."),
        ("Reading stories helps me improve my vocabulary.", "Lire des histoires m'aide à améliorer mon vocabulaire."),
        ("She dreams of visiting museums in London.", "Elle rêve de visiter des musées à Londres."),
        ("We must recycle to protect the environment.", "Nous devons recycler pour protéger l'environnement."),
    ],
}

CALENDAR_VOCAB: Dict[str, Dict[str, str]] = {
    "beginner": {
        "lundi": "Monday",
        "mardi": "Tuesday",
        "mercredi": "Wednesday",
        "jeudi": "Thursday",
        "vendredi": "Friday",
        "samedi": "Saturday",
        "dimanche": "Sunday",
    },
    "intermediate": {
        "janvier": "January",
        "février": "February",
        "mars": "March",
        "avril": "April",
        "mai": "May",
        "juin": "June",
        "juillet": "July",
        "août": "August",
        "septembre": "September",
        "octobre": "October",
        "novembre": "November",
        "décembre": "December",
    },
    "advanced": {
        "printemps": "spring",
        "été": "summer",
        "automne": "autumn",
        "hiver": "winter",
        "la veille": "the day before",
        "le lendemain": "the day after",
    },
}

FAMILY_VOCAB: Dict[str, Dict[str, str]] = {
    "beginner": {
        "mère": "mother",
        "père": "father",
        "frère": "brother",
        "soeur": "sister",
        "grand-mère": "grandmother",
        "grand-père": "grandfather",
    },
    "intermediate": {
        "tante": "aunt",
        "oncle": "uncle",
        "cousin": "cousin",
        "cousine": "cousin",
        "bébé": "baby",
        "parents": "parents",
    },
    "advanced": {
        "famille proche": "close family",
        "filleule": "goddaughter",
        "filleul": "godson",
        "demi-frère": "half-brother",
        "demi-soeur": "half-sister",
    },
}

SCHOOL_VOCAB: Dict[str, Dict[str, str]] = {
    "beginner": {
        "professeur": "teacher",
        "élève": "pupil",
        "classe": "classroom",
        "bureau": "desk",
        "chaise": "chair",
        "livre": "book",
    },
    "intermediate": {
        "craie": "chalk",
        "règle": "ruler",
        "gomme": "eraser",
        "carte": "map",
        "laboratoire": "lab",
        "cahier": "exercise book",
    },
    "advanced": {
        "emploi du temps": "timetable",
        "matière": "subject",
        "évaluation": "assessment",
        "correspondant": "pen pal",
        "bibliothécaire": "librarian",
    },
}

DAILY_ROUTINE: Dict[str, Dict[str, str]] = {
    "beginner": {
        "se lever": "to get up",
        "prendre le petit déjeuner": "to have breakfast",
        "aller à l'école": "to go to school",
        "faire ses devoirs": "to do homework",
        "se coucher": "to go to bed",
    },
    "intermediate": {
        "se brosser les dents": "to brush one's teeth",
        "préparer son cartable": "to pack one's schoolbag",
        "jouer dehors": "to play outside",
        "aider à mettre la table": "to help set the table",
        "s'entraîner au sport": "to practise sport",
    },
    "advanced": {
        "réviser une leçon": "to review a lesson",
        "participer à un club": "to join a club",
        "surfer sur Internet": "to surf the Internet",
        "discuter avec ses amis": "to chat with friends",
        "prendre soin d'un animal": "to look after a pet",
    },
}

HOBBIES_VOCAB: Dict[str, Dict[str, str]] = {
    "beginner": {
        "lire": "to read",
        "dessiner": "to draw",
        "chanter": "to sing",
        "danser": "to dance",
        "jouer au football": "to play football",
    },
    "intermediate": {
        "faire du vélo": "to ride a bike",
        "jouer d'un instrument": "to play an instrument",
        "cuisiner": "to cook",
        "regarder un film": "to watch a film",
        "faire du théâtre": "to act",
    },
    "advanced": {
        "faire de la randonnée": "to go hiking",
        "écrire des histoires": "to write stories",
        "faire de la photographie": "to do photography",
        "collectionner des timbres": "to collect stamps",
        "apprendre une chorégraphie": "to learn a choreography",
    },
}

PRESENT_SIMPLE_ITEMS: Dict[str, List[Tuple[str, str]]] = {
    "beginner": [
        ("Complète : I ___ (to be) eleven years old.", "am"),
        ("Complète : She ___ (to like) English lessons.", "likes"),
        ("Complète : We ___ (to have) math on Monday.", "have"),
    ],
    "intermediate": [
        ("Complète : He ___ (to go) to school by bus.", "goes"),
        ("Complète : They ___ (to watch) TV after dinner.", "watch"),
        ("Complète : My brother ___ (to study) French.", "studies"),
    ],
    "advanced": [
        ("Complète : The club ___ (to meet) every Thursday evening.", "meets"),
        ("Complète : My friends ___ (to do) their homework together.", "do"),
        ("Complète : The teacher ___ (to explain) the project clearly.", "explains"),
    ],
}

PRONOUN_ITEMS: Dict[str, List[Tuple[str, str]]] = {
    "beginner": [
        ("Choisis le bon pronom : ___ is my sister (she/her).", "she"),
        ("Complète : This is ___ pencil (my/me).", "my"),
        ("Complète : These books are ___ (their/them).", "theirs"),
    ],
    "intermediate": [
        ("Complète : Give the ball to ___ (us/we).", "us"),
        ("Complète : That seat is ___ (his/he).", "his"),
        ("Complète : Julie is taller than ___ (me/I).", "me"),
    ],
    "advanced": [
        ("Choisis le bon pronom : The choice is ___ (yours/your).", "yours"),
        ("Complète : The house at the corner is ___ (ours/us).", "ours"),
        ("Complète : Between you and ___, I prefer music (I/me).", "me"),
    ],
}

CULTURE_ITEMS: Dict[str, List[Tuple[str, str]]] = {
    "intermediate": [
        ("Quelle est la capitale du Royaume-Uni ?", "London"),
        ("Comment appelle-t-on les habitants des États-Unis en anglais ?", "Americans"),
        ("Quel océan sépare la France du Canada ?", "Atlantic Ocean"),
    ],
    "advanced": [
        ("Cite un pays d'Afrique où l'anglais est langue officielle.", "South Africa"),
        ("Quel monument célèbre se trouve à New York et symbolise l'accueil ?", "Statue of Liberty"),
        ("Quel est le surnom du drapeau du Royaume-Uni ?", "Union Jack"),
    ],
}

ADJECTIVE_OPPOSITES: Dict[str, List[Tuple[str, str]]] = {
    "intermediate": [
        ("Donne l'opposé de 'big' en anglais.", "small"),
        ("Donne l'opposé de 'cold' en anglais.", "hot"),
        ("Donne l'opposé de 'happy' en anglais.", "sad"),
    ],
    "advanced": [
        ("Donne l'opposé de 'noisy' en anglais.", "quiet"),
        ("Donne l'opposé de 'expensive' en anglais.", "cheap"),
        ("Donne l'opposé de 'light' (lourd/léger) en anglais.", "heavy"),
    ],
}


def normalize_difficulty(raw_value: Optional[str]) -> str:
    if not raw_value:
        return DIFFICULTY_LEVELS[0]
    value = raw_value.lower().strip()
    if value in DIFFICULTY_LEVELS:
        return value
    return DIFFICULTY_LEVELS[0]


def _pooled_dict(data: Dict[str, Dict[str, str]], difficulty: str) -> Dict[str, str]:
    merged: Dict[str, str] = {}
    for level in DIFFICULTY_LEVELS:
        merged.update(data.get(level, {}))
        if level == difficulty:
            break
    if merged:
        return merged
    # fallback if nothing is available
    for level in DIFFICULTY_LEVELS:
        if data.get(level):
            return data[level]
    return {}


def _pooled_list(data: Dict[str, List[Tuple[str, str]]], difficulty: str) -> List[Tuple[str, str]]:
    merged: List[Tuple[str, str]] = []
    for level in DIFFICULTY_LEVELS:
        merged.extend(data.get(level, []))
        if level == difficulty:
            break
    if merged:
        return merged
    for level in DIFFICULTY_LEVELS:
        if data.get(level):
            return data[level]
    return []


def _number_range_for_level(difficulty: str) -> range:
    if difficulty == "beginner":
        return range(0, 51)
    if difficulty == "intermediate":
        return range(0, 201)
    return range(0, 1000)


def _number_to_words(value: int) -> str:
    if value < 20:
        return UNITS_AND_TEENS[value]
    if value < 100:
        tens, ones = divmod(value, 10)
        tens_word = TENS_WORDS[tens * 10]
        if ones:
            return f"{tens_word}-{UNITS_AND_TEENS[ones]}"
        return tens_word
    if value < 1000:
        hundreds, remainder = divmod(value, 100)
        base = f"{UNITS_AND_TEENS[hundreds]} hundred"
        if remainder:
            return f"{base} and {_number_to_words(remainder)}"
        return base
    return str(value)


def _generate_number_word_exercise(difficulty: str) -> ExercisePrompt:
    number = random.choice(list(_number_range_for_level(difficulty)))
    return ExercisePrompt(
        prompt=f"Écris en anglais le nombre {number}.",
        answer=_number_to_words(number),
        category="number_word",
    )


def _generate_word_number_exercise(difficulty: str) -> ExercisePrompt:
    number = random.choice(list(_number_range_for_level(difficulty)))
    return ExercisePrompt(
        prompt=f"Écris en chiffres le nombre '{_number_to_words(number)}'.",
        answer=str(number),
        category="word_number",
    )


def _generate_translation_fr_en(difficulty: str) -> ExercisePrompt:
    pool = _pooled_dict(FR_EN_TRANSLATIONS, difficulty)
    french, english = random.choice(list(pool.items()))
    return ExercisePrompt(
        prompt=f"Traduis en anglais : '{french}'.",
        answer=english,
        category="translate_fr_en",
    )


def _generate_translation_en_fr(difficulty: str) -> ExercisePrompt:
    pool = _pooled_dict(FR_EN_TRANSLATIONS, difficulty)
    english, french = random.choice([(value, key) for key, value in pool.items()])
    return ExercisePrompt(
        prompt=f"Traduis en français : '{english}'.",
        answer=french,
        category="translate_en_fr",
    )


def _generate_sentence_translation(difficulty: str) -> ExercisePrompt:
    pool = _pooled_list(SENTENCE_BANK, difficulty)
    if not pool:
        return ExercisePrompt("Phrase manquante", "", "sentence_en_fr")
    english, french = random.choice(pool)
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


def _time_to_words(hour: int, minute: int) -> str:
    hour = ((hour - 1) % 12) + 1
    hour_word = HOUR_WORDS[hour]
    if minute == 0:
        return f"{hour_word} o'clock"
    if minute == 15:
        return f"quarter past {hour_word}"
    if minute == 30:
        return f"half past {hour_word}"
    if minute == 45:
        next_hour = HOUR_WORDS[((hour) % 12) + 1]
        return f"quarter to {next_hour}"
    if minute < 30:
        minute_word = _number_to_words(minute).replace("-", " ")
        return f"{minute_word} past {hour_word}"
    next_hour = HOUR_WORDS[((hour) % 12) + 1]
    minute_word = _number_to_words(60 - minute).replace("-", " ")
    return f"{minute_word} to {next_hour}"


def _generate_time_reading_exercise(difficulty: str) -> ExercisePrompt:
    if difficulty == "beginner":
        minutes_options = [0, 15, 30]
    elif difficulty == "intermediate":
        minutes_options = [0, 15, 20, 25, 30, 35, 45]
    else:
        minutes_options = [0, 5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55]
    hour = random.randint(1, 12 if difficulty != "advanced" else 24)
    minute = random.choice(minutes_options)
    answer = _time_to_words(hour, minute)
    prompt_time = f"{hour:02d}:{minute:02d}"
    return ExercisePrompt(
        prompt=f"Écris en toutes lettres en anglais l'heure {prompt_time}.",
        answer=answer,
        category="time_reading",
    )


def _generate_calendar_vocabulary(difficulty: str) -> ExercisePrompt:
    pool = _pooled_dict(CALENDAR_VOCAB, difficulty)
    french, english = random.choice(list(pool.items()))
    return ExercisePrompt(
        prompt=f"Traduis en anglais : '{french}'.",
        answer=english,
        category="calendar_vocab",
    )


def _generate_family_vocabulary(difficulty: str) -> ExercisePrompt:
    pool = _pooled_dict(FAMILY_VOCAB, difficulty)
    french, english = random.choice(list(pool.items()))
    return ExercisePrompt(
        prompt=f"Comment dit-on '{french}' en anglais ?",
        answer=english,
        category="family_vocab",
    )


def _generate_school_vocabulary(difficulty: str) -> ExercisePrompt:
    pool = _pooled_dict(SCHOOL_VOCAB, difficulty)
    french, english = random.choice(list(pool.items()))
    return ExercisePrompt(
        prompt=f"Traduis ce mot de l'école en anglais : '{french}'.",
        answer=english,
        category="school_vocab",
    )


def _generate_daily_routine(difficulty: str) -> ExercisePrompt:
    pool = _pooled_dict(DAILY_ROUTINE, difficulty)
    french, english = random.choice(list(pool.items()))
    return ExercisePrompt(
        prompt=f"Traduis en anglais cette action quotidienne : '{french}'.",
        answer=english,
        category="daily_routine",
    )


def _generate_hobbies_vocabulary(difficulty: str) -> ExercisePrompt:
    pool = _pooled_dict(HOBBIES_VOCAB, difficulty)
    french, english = random.choice(list(pool.items()))
    return ExercisePrompt(
        prompt=f"Comment dit-on ce loisir en anglais : '{french}' ?",
        answer=english,
        category="hobbies_vocab",
    )


def _generate_present_simple(difficulty: str) -> ExercisePrompt:
    pool = _pooled_list(PRESENT_SIMPLE_ITEMS, difficulty)
    statement, answer = random.choice(pool)
    return ExercisePrompt(
        prompt=statement,
        answer=answer,
        category="grammar_present_simple",
    )


def _generate_pronoun_exercise(difficulty: str) -> ExercisePrompt:
    pool = _pooled_list(PRONOUN_ITEMS, difficulty)
    statement, answer = random.choice(pool)
    return ExercisePrompt(
        prompt=statement,
        answer=answer,
        category="grammar_pronouns",
    )


def _generate_culture_item(difficulty: str) -> ExercisePrompt:
    pool = _pooled_list(CULTURE_ITEMS, difficulty)
    statement, answer = random.choice(pool)
    return ExercisePrompt(
        prompt=statement,
        answer=answer,
        category="culture_countries",
    )


def _generate_adjective_opposite(difficulty: str) -> ExercisePrompt:
    pool = _pooled_list(ADJECTIVE_OPPOSITES, difficulty)
    statement, answer = random.choice(pool)
    return ExercisePrompt(
        prompt=statement,
        answer=answer,
        category="adjectives_opposites",
    )


GENERATOR_REGISTRY: List[GeneratorSpec] = [
    GeneratorSpec(("beginner", "intermediate", "advanced"), _generate_number_word_exercise),
    GeneratorSpec(("beginner", "intermediate", "advanced"), _generate_word_number_exercise),
    GeneratorSpec(("beginner", "intermediate", "advanced"), _generate_translation_fr_en),
    GeneratorSpec(("beginner", "intermediate", "advanced"), _generate_translation_en_fr),
    GeneratorSpec(("beginner", "intermediate", "advanced"), _generate_sentence_translation),
    GeneratorSpec(("beginner", "intermediate", "advanced"), _generate_time_reading_exercise),
    GeneratorSpec(("beginner", "intermediate", "advanced"), _generate_calendar_vocabulary),
    GeneratorSpec(("beginner", "intermediate", "advanced"), _generate_family_vocabulary),
    GeneratorSpec(("beginner", "intermediate", "advanced"), _generate_school_vocabulary),
    GeneratorSpec(("beginner", "intermediate", "advanced"), _generate_daily_routine),
    GeneratorSpec(("beginner", "intermediate", "advanced"), _generate_hobbies_vocabulary),
    GeneratorSpec(("beginner", "intermediate", "advanced"), _generate_present_simple),
    GeneratorSpec(("beginner", "intermediate", "advanced"), _generate_pronoun_exercise),
    GeneratorSpec(("intermediate", "advanced"), _generate_culture_item),
    GeneratorSpec(("intermediate", "advanced"), _generate_adjective_opposite),
]


def generate_default_exercises(quantity: int = 20, difficulty: str = "beginner") -> List[ExercisePrompt]:
    normalized = normalize_difficulty(difficulty)
    exercises: List[ExercisePrompt] = []
    eligible = [spec for spec in GENERATOR_REGISTRY if normalized in spec.difficulties]
    fallback = GENERATOR_REGISTRY or eligible

    for _ in range(quantity):
        spec = random.choice(eligible or fallback)
        exercises.append(spec.builder(normalized))
    return exercises
