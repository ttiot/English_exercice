import random
from dataclasses import dataclass, field
from typing import Callable, Dict, Iterable, List, Optional, Sequence, Tuple


@dataclass(frozen=True)
class ExercisePrompt:
    """Représente un exercice prêt à être joué.

    Les champs ``question_type``, ``options`` et ``accepted_answers`` sont
    optionnels pour rester rétro-compatibles avec les générateurs historiques
    qui produisent uniquement des questions textuelles.

    - ``question_type='text'`` : saisie libre (défaut).
    - ``question_type='mcq'`` : l'élève doit choisir une valeur exacte de
      ``options``. ``answer`` doit aussi figurer dans ``options``.
    - ``question_type='word_bank'`` : saisie libre, mais ``options`` est
      affichée comme banque de mots à piocher.

    ``accepted_answers`` liste les variantes acceptées en plus de ``answer``
    (utile pour les traductions à plusieurs formulations valides).
    """

    prompt: str
    answer: str
    category: str
    question_type: str = "text"
    options: Tuple[str, ...] = field(default_factory=tuple)
    accepted_answers: Tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class GeneratorSpec:
    difficulties: Sequence[str]
    category: str
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

PRESENT_SIMPLE_SUBJECTS: Dict[str, List[str]] = {
    "beginner": ["I", "you", "he", "she", "we", "they"],
    "intermediate": ["my brother", "her parents", "the class", "our teacher", "my friends"],
    "advanced": ["the committee", "each student", "the headmaster", "every visitor", "the science club"],
}

PRESENT_SIMPLE_VERBS: Dict[str, List[str]] = {
    "beginner": ["play", "like", "go", "have", "eat", "watch"],
    "intermediate": ["study", "finish", "carry", "miss", "do", "read"],
    "advanced": ["organize", "discuss", "prefer", "travel", "explain", "practice"],
}

PRESENT_SIMPLE_COMPLEMENTS: Dict[str, List[str]] = {
    "beginner": ["to school by bus", "every day", "in the morning", "after lunch"],
    "intermediate": ["after dinner", "on Mondays", "with their friends", "in the library"],
    "advanced": ["every Thursday evening", "when the bell rings", "before the project starts", "during the break"],
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

# --- Mots interrogatifs (priorité pour le fils du user) -------------------

# Phrases à compléter par UN mot interrogatif. Chaque entrée doit avoir
# une réponse non-ambiguë. Distractors sont piochés dans INTERROGATIVE_WORDS.
INTERROGATIVE_WORDS: Tuple[str, ...] = (
    "What", "When", "Who", "Why", "How", "Where", "Which",
)

INTERROGATIVE_COMPLETIONS: Dict[str, List[Tuple[str, str]]] = {
    "beginner": [
        ("___ is your name?", "What"),
        ("___ do you live?", "Where"),
        ("___ are you?", "How"),
        ("___ is your birthday?", "When"),
        ("___ is your best friend?", "Who"),
        ("___ is your favourite colour?", "What"),
        ("___ do you go to school?", "How"),
        ("___ are you going?", "Where"),
        ("___ old are you?", "How"),
        ("___ is your teacher?", "Who"),
        ("___ is your favourite food?", "What"),
        ("___ is the weather like?", "How"),
        ("___ are you sad?", "Why"),
        ("___ is the cat?", "Where"),
    ],
    "intermediate": [
        ("___ do you eat for lunch?", "What"),
        ("___ subject do you prefer, maths or English?", "Which"),
        ("___ does the lesson start?", "When"),
        ("___ many books are in your bag?", "How"),
        ("___ are you laughing?", "Why"),
        ("___ team do you support?", "Which"),
        ("___ wins the race?", "Who"),
        ("___ are you doing this evening?", "What"),
        ("___ do you take the bus?", "When"),
        ("___ much sugar do you want?", "How"),
    ],
    "advanced": [
        ("___ do you usually wake up on Saturdays?", "When"),
        ("___ would you like to visit, London or New York?", "Which"),
        ("___ on earth did you do that?", "Why"),
        ("___ can I help you with today?", "How"),
        ("___ are you waiting for at the station?", "Who"),
        ("___ have you been since last summer?", "Where"),
    ],
}

INTERROGATIVE_TRANSLATIONS: Dict[str, List[Tuple[str, str]]] = {
    # Pairs (anglais, français) — utilisées dans les 2 directions.
    "beginner": [
        ("What is your name?", "Quel est ton nom ?"),
        ("Where do you live?", "Où habites-tu ?"),
        ("When is your birthday?", "Quand est ton anniversaire ?"),
        ("Who is your best friend?", "Qui est ton meilleur ami ?"),
        ("How are you?", "Comment vas-tu ?"),
        ("Why are you happy?", "Pourquoi es-tu content ?"),
        ("How old are you?", "Quel âge as-tu ?"),
        ("What is your favourite colour?", "Quelle est ta couleur préférée ?"),
        ("Where is the cat?", "Où est le chat ?"),
        ("Who is your teacher?", "Qui est ton professeur ?"),
    ],
    "intermediate": [
        ("What do you eat for lunch?", "Qu'est-ce que tu manges pour le déjeuner ?"),
        ("When does school start?", "Quand commence l'école ?"),
        ("Why do you like English?", "Pourquoi aimes-tu l'anglais ?"),
        ("How many sisters do you have?", "Combien de sœurs as-tu ?"),
        ("Which colour do you prefer?", "Quelle couleur préfères-tu ?"),
        ("Where do you go on holiday?", "Où vas-tu en vacances ?"),
        ("Who cooks dinner in your family?", "Qui prépare le dîner chez toi ?"),
    ],
    "advanced": [
        ("How often do you go to the cinema?", "À quelle fréquence vas-tu au cinéma ?"),
        ("Which of these books did you enjoy the most?", "Lequel de ces livres as-tu préféré ?"),
        ("Where would you like to live in the future?", "Où aimerais-tu vivre plus tard ?"),
    ],
}

# --- Vocabulaire alimentation (PDF "Alimentation 6e") --------------------

FOOD_VOCAB: Dict[str, Dict[str, str]] = {
    "beginner": {
        "une pomme": "apple",
        "une banane": "banana",
        "du pain": "bread",
        "du fromage": "cheese",
        "de l'eau": "water",
        "du lait": "milk",
        "du jus de fruit": "fruit juice",
        "un œuf": "egg",
        "du riz": "rice",
        "un sandwich": "sandwich",
        "une pizza": "pizza",
        "une orange": "orange",
        "du chocolat": "chocolate",
        "du beurre": "butter",
        "du sucre": "sugar",
        "du poulet": "chicken",
    },
    "intermediate": {
        "une fraise": "strawberry",
        "une glace": "ice cream",
        "un petit-déjeuner": "breakfast",
        "du jambon": "ham",
        "un soda": "soda",
        "du miel": "honey",
        "des carottes": "carrots",
        "du café": "coffee",
        "une tomate": "tomato",
        "une salade": "salad",
        "une soupe": "soup",
        "des pâtes": "pasta",
        "du yaourt": "yogurt",
        "une crêpe": "pancake",
        "de la confiture": "jam",
        "du poisson": "fish",
        "une poire": "pear",
    },
    "advanced": {
        "des framboises": "raspberries",
        "un ananas": "pineapple",
        "des champignons": "mushrooms",
        "du saumon": "salmon",
        "des frites": "chips",
        "un dessert": "dessert",
        "du raisin": "grapes",
        "une noisette": "hazelnut",
    },
}

# --- Vocabulaire corps -----------------------------------------------------

BODY_VOCAB: Dict[str, Dict[str, str]] = {
    "beginner": {
        "la tête": "head",
        "la main": "hand",
        "le pied": "foot",
        "l'œil": "eye",
        "l'oreille": "ear",
        "le nez": "nose",
        "la bouche": "mouth",
        "le bras": "arm",
        "la jambe": "leg",
        "les cheveux": "hair",
        "le doigt": "finger",
        "les dents": "teeth",
    },
    "intermediate": {
        "l'épaule": "shoulder",
        "le coude": "elbow",
        "le genou": "knee",
        "la cheville": "ankle",
        "le poignet": "wrist",
        "le dos": "back",
        "le ventre": "stomach",
        "le cou": "neck",
    },
    "advanced": {
        "le menton": "chin",
        "le sourcil": "eyebrow",
        "la mâchoire": "jaw",
        "le talon": "heel",
    },
}

# --- Vocabulaire vêtements -------------------------------------------------

CLOTHES_VOCAB: Dict[str, Dict[str, str]] = {
    "beginner": {
        "un t-shirt": "t-shirt",
        "un pantalon": "trousers",
        "une jupe": "skirt",
        "une robe": "dress",
        "un manteau": "coat",
        "un pull": "jumper",
        "des chaussures": "shoes",
        "une chaussette": "sock",
        "un chapeau": "hat",
        "une casquette": "cap",
        "une écharpe": "scarf",
        "des gants": "gloves",
    },
    "intermediate": {
        "une veste": "jacket",
        "un short": "shorts",
        "des baskets": "trainers",
        "une ceinture": "belt",
        "une chemise": "shirt",
        "un sweat à capuche": "hoodie",
        "un maillot de bain": "swimsuit",
        "des bottes": "boots",
    },
    "advanced": {
        "un costume": "suit",
        "un imperméable": "raincoat",
        "des sandales": "sandals",
        "un nœud papillon": "bow tie",
    },
}

# --- Vocabulaire météo -----------------------------------------------------

WEATHER_VOCAB: Dict[str, Dict[str, str]] = {
    "beginner": {
        "ensoleillé": "sunny",
        "pluvieux": "rainy",
        "nuageux": "cloudy",
        "venteux": "windy",
        "neigeux": "snowy",
        "chaud": "hot",
        "froid": "cold",
        "le soleil": "sun",
        "la pluie": "rain",
        "la neige": "snow",
        "le vent": "wind",
    },
    "intermediate": {
        "orageux": "stormy",
        "brumeux": "foggy",
        "humide": "humid",
        "frais": "cool",
        "doux": "mild",
        "un nuage": "cloud",
        "un orage": "thunderstorm",
        "un éclair": "lightning",
    },
    "advanced": {
        "verglacé": "icy",
        "bruineux": "drizzly",
        "une rafale": "gust",
        "une averse": "shower",
    },
}

# --- Phrases à transformer en 3e personne (PDF Daily Routine, Ex.6) -------

# Format: (verbe_base, complément SANS PONCTUATION FINALE). Le générateur
# reconstitue "I {verbe} {complément}." pour l'énoncé et conjugue à la 3e
# personne pour la réponse, en piochant un prénom dans THIRD_PERSON_PEOPLE
# et en remplaçant "my" par "his/her" selon le genre.
THIRD_PERSON_SENTENCES: Dict[str, List[Tuple[str, str]]] = {
    "beginner": [
        ("wake up", "at 7"),
        ("have", "breakfast at 7:30"),
        ("go", "to school by bus"),
        ("watch", "TV in the evening"),
        ("brush", "my teeth after dinner"),
        ("play", "football after school"),
        ("do", "my homework at 5pm"),
        ("read", "a book before bed"),
        ("wash", "my hands"),
        ("finish", "school at 4"),
    ],
    "intermediate": [
        ("study", "English at school"),
        ("listen", "to music every day"),
        ("ride", "my bike on Sundays"),
        ("eat", "lunch at the canteen"),
        ("walk", "to the park"),
        ("write", "a letter to my friend"),
    ],
    "advanced": [
        ("organise", "a party for my birthday"),
        ("practise", "the piano twice a week"),
        ("travel", "to England every summer"),
    ],
}

# (prénom, possessif_3e_personne)
THIRD_PERSON_PEOPLE: Tuple[Tuple[str, str], ...] = (
    ("Tom", "his"),
    ("Emma", "her"),
    ("Lucas", "his"),
    ("Mia", "her"),
    ("Léa", "her"),
    ("Noah", "his"),
)


def normalize_difficulty(raw_value: Optional[str]) -> str:
    if not raw_value:
        return DIFFICULTY_LEVELS[0]
    value = raw_value.lower().strip()
    if value in DIFFICULTY_LEVELS:
        return value
    return DIFFICULTY_LEVELS[0]


def _custom_items(category: Optional[str], difficulty: str) -> List[ExercisePrompt]:
    try:
        from .models import ExerciseItem, QuestionCategory
    except Exception:
        return []
    if not category:
        return []
    try:
        items = (
            ExerciseItem.query.join(QuestionCategory)
            .filter(
                QuestionCategory.code == category,
                ExerciseItem.is_active.is_(True),
                ExerciseItem.difficulty.in_([difficulty, "any"]),
            )
            .all()
        )
    except Exception:
        return []
    return [
        ExercisePrompt(prompt=item.prompt, answer=item.answer, category=category)
        for item in items
    ]


def _random_custom_item(category: Optional[str], difficulty: str) -> Optional[ExercisePrompt]:
    items = _custom_items(category, difficulty)
    if not items:
        return None
    return random.choice(items)


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


def _is_third_person_singular(subject: str) -> bool:
    lowered = subject.strip().lower()
    return lowered in {"he", "she", "it"} or not any(
        lowered.startswith(token) for token in {"i", "you", "we", "they"}
    )


def _conjugate_present_simple(subject: str, base: str) -> str:
    if not _is_third_person_singular(subject):
        return base
    if base.endswith(("ch", "sh", "x", "s", "z", "o")):
        return f"{base}es"
    if base.endswith("y") and len(base) > 1 and base[-2] not in "aeiou":
        return f"{base[:-1]}ies"
    return f"{base}s"


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
    return ExercisePrompt(
        prompt=f"Traduis en français : '{english}'.",
        answer=french,
        category="sentence_en_fr",
    )


def _generate_sentence_fr_en(difficulty: str) -> ExercisePrompt:
    pool = _pooled_list(SENTENCE_BANK, difficulty)
    if not pool:
        return ExercisePrompt("Phrase manquante", "", "sentence_fr_en")
    english, french = random.choice(pool)
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
    level_items = PRESENT_SIMPLE_ITEMS.get(difficulty) or []
    if level_items and random.random() < 0.5:
        statement, answer = random.choice(level_items)
        return ExercisePrompt(
            prompt=statement,
            answer=answer,
            category="grammar_present_simple",
        )

    subject_pool = PRESENT_SIMPLE_SUBJECTS.get(difficulty) or PRESENT_SIMPLE_SUBJECTS["beginner"]
    verb_pool = PRESENT_SIMPLE_VERBS.get(difficulty) or PRESENT_SIMPLE_VERBS["beginner"]
    complement_pool = PRESENT_SIMPLE_COMPLEMENTS.get(difficulty) or PRESENT_SIMPLE_COMPLEMENTS["beginner"]
    subject = random.choice(subject_pool)
    base_verb = random.choice(verb_pool)
    complement = random.choice(complement_pool)
    answer = _conjugate_present_simple(subject, base_verb)
    return ExercisePrompt(
        prompt=f"Complète : {subject} ___ {complement} ({base_verb}).",
        answer=answer,
        category="grammar_present_simple",
    )


def _generate_pronoun_exercise(difficulty: str) -> ExercisePrompt:
    pool = PRONOUN_ITEMS.get(difficulty) or _pooled_list(PRONOUN_ITEMS, difficulty)
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


def _generate_interrogative_completion(difficulty: str) -> ExercisePrompt:
    """QCM : choisir le bon mot interrogatif pour compléter la phrase."""
    pool = _pooled_list(INTERROGATIVE_COMPLETIONS, difficulty)
    sentence, answer = random.choice(pool)
    distractors = [w for w in INTERROGATIVE_WORDS if w != answer]
    options = random.sample(distractors, k=4) + [answer]
    random.shuffle(options)
    return ExercisePrompt(
        prompt=f"Complète avec le bon mot interrogatif : {sentence}",
        answer=answer,
        category="interrogative_words",
        question_type="mcq",
        options=tuple(options),
    )


def _generate_interrogative_translation(difficulty: str) -> ExercisePrompt:
    """Traduction d'une question dans un sens ou l'autre, au hasard."""
    pool = _pooled_list(INTERROGATIVE_TRANSLATIONS, difficulty)
    english, french = random.choice(pool)
    if random.random() < 0.5:
        return ExercisePrompt(
            prompt=f"Traduis en anglais : « {french} »",
            answer=english,
            category="interrogative_words",
        )
    return ExercisePrompt(
        prompt=f"Traduis en français : « {english} »",
        answer=french,
        category="interrogative_words",
    )


def _bidirectional_vocab_exercise(
    pool: Dict[str, str], category: str, theme_label_fr: str
) -> ExercisePrompt:
    """Helper : tire une paire FR/EN, choisit la direction au hasard."""
    french, english = random.choice(list(pool.items()))
    if random.random() < 0.5:
        return ExercisePrompt(
            prompt=f"Traduis en anglais ({theme_label_fr}) : « {french} »",
            answer=english,
            category=category,
        )
    return ExercisePrompt(
        prompt=f"Traduis en français ({theme_label_fr}) : « {english} »",
        answer=french,
        category=category,
    )


def _generate_food_vocabulary(difficulty: str) -> ExercisePrompt:
    return _bidirectional_vocab_exercise(
        _pooled_dict(FOOD_VOCAB, difficulty), "food_vocab", "alimentation"
    )


def _generate_body_vocabulary(difficulty: str) -> ExercisePrompt:
    return _bidirectional_vocab_exercise(
        _pooled_dict(BODY_VOCAB, difficulty), "body_vocab", "corps"
    )


def _generate_clothes_vocabulary(difficulty: str) -> ExercisePrompt:
    return _bidirectional_vocab_exercise(
        _pooled_dict(CLOTHES_VOCAB, difficulty), "clothes_vocab", "vêtements"
    )


def _generate_weather_vocabulary(difficulty: str) -> ExercisePrompt:
    return _bidirectional_vocab_exercise(
        _pooled_dict(WEATHER_VOCAB, difficulty), "weather_vocab", "météo"
    )


def _generate_third_person_s(difficulty: str) -> ExercisePrompt:
    """Réécrit une phrase en « I … » à la 3e personne du singulier.

    Ex : ``I wake up at 7`` ➜ ``Tom wakes up at 7.`` Couvre les cas
    spéciaux (go→goes, watch→watches, have→has, do→does, brush→brushes…)
    et remplace ``my`` par ``his``/``her`` selon le prénom.
    """
    pool = _pooled_list(THIRD_PERSON_SENTENCES, difficulty)
    base_verb, rest = random.choice(pool)
    name, possessive = random.choice(THIRD_PERSON_PEOPLE)
    # Verbe à particule (« wake up », « get up ») : on conjugue le 1er mot.
    head, _, particle = base_verb.partition(" ")
    if head == "have":
        head_conj = "has"
    else:
        head_conj = _conjugate_present_simple(name, head)
    conjugated = f"{head_conj} {particle}".strip()
    rest_third = " ".join(possessive if word == "my" else word for word in rest.split())
    if rest:
        original = f"I {base_verb} {rest}."
        rewritten = f"{name} {conjugated} {rest_third}."
    else:
        original = f"I {base_verb}."
        rewritten = f"{name} {conjugated}."
    return ExercisePrompt(
        prompt=f"Réécris cette phrase avec « {name} » : {original}",
        answer=rewritten,
        category="grammar_third_person_s",
    )


GENERATOR_REGISTRY: List[GeneratorSpec] = [
    GeneratorSpec(("beginner", "intermediate", "advanced"), "number_word", _generate_number_word_exercise),
    GeneratorSpec(("beginner", "intermediate", "advanced"), "word_number", _generate_word_number_exercise),
    GeneratorSpec(("beginner", "intermediate", "advanced"), "translate_fr_en", _generate_translation_fr_en),
    GeneratorSpec(("beginner", "intermediate", "advanced"), "translate_en_fr", _generate_translation_en_fr),
    GeneratorSpec(("beginner", "intermediate", "advanced"), "sentence_en_fr", _generate_sentence_translation),
    GeneratorSpec(("beginner", "intermediate", "advanced"), "sentence_fr_en", _generate_sentence_fr_en),
    GeneratorSpec(("beginner", "intermediate", "advanced"), "time_reading", _generate_time_reading_exercise),
    GeneratorSpec(("beginner", "intermediate", "advanced"), "calendar_vocab", _generate_calendar_vocabulary),
    GeneratorSpec(("beginner", "intermediate", "advanced"), "family_vocab", _generate_family_vocabulary),
    GeneratorSpec(("beginner", "intermediate", "advanced"), "school_vocab", _generate_school_vocabulary),
    GeneratorSpec(("beginner", "intermediate", "advanced"), "daily_routine", _generate_daily_routine),
    GeneratorSpec(("beginner", "intermediate", "advanced"), "hobbies_vocab", _generate_hobbies_vocabulary),
    GeneratorSpec(("beginner", "intermediate", "advanced"), "grammar_present_simple", _generate_present_simple),
    GeneratorSpec(("beginner", "intermediate", "advanced"), "grammar_pronouns", _generate_pronoun_exercise),
    GeneratorSpec(("intermediate", "advanced"), "culture_countries", _generate_culture_item),
    GeneratorSpec(("intermediate", "advanced"), "adjectives_opposites", _generate_adjective_opposite),
    GeneratorSpec(("beginner", "intermediate", "advanced"), "interrogative_words", _generate_interrogative_completion),
    GeneratorSpec(("beginner", "intermediate", "advanced"), "interrogative_words", _generate_interrogative_translation),
    GeneratorSpec(("beginner", "intermediate", "advanced"), "food_vocab", _generate_food_vocabulary),
    GeneratorSpec(("beginner", "intermediate", "advanced"), "body_vocab", _generate_body_vocabulary),
    GeneratorSpec(("beginner", "intermediate", "advanced"), "clothes_vocab", _generate_clothes_vocabulary),
    GeneratorSpec(("beginner", "intermediate", "advanced"), "weather_vocab", _generate_weather_vocabulary),
    GeneratorSpec(("beginner", "intermediate", "advanced"), "grammar_third_person_s", _generate_third_person_s),
]

AVAILABLE_CATEGORIES: Tuple[str, ...] = tuple(sorted({spec.category for spec in GENERATOR_REGISTRY}))


def generate_default_exercises(quantity: int = 20, difficulty: str = "beginner") -> List[ExercisePrompt]:
    normalized = normalize_difficulty(difficulty)
    exercises: List[ExercisePrompt] = []
    eligible = [spec for spec in GENERATOR_REGISTRY if normalized in spec.difficulties]
    fallback = eligible or GENERATOR_REGISTRY
    custom_categories = list({spec.category for spec in GENERATOR_REGISTRY})

    seen_signatures = set()
    attempts = 0
    max_attempts = max(10, quantity * 10)

    while len(exercises) < quantity and attempts < max_attempts:
        custom_prompt = None
        if custom_categories and random.random() < 0.35:
            custom_prompt = _random_custom_item(random.choice(custom_categories), normalized)
        if custom_prompt:
            prompt = custom_prompt
        else:
            spec = random.choice(eligible or fallback)
            prompt = spec.builder(normalized)
        signature = (prompt.category, prompt.prompt.strip().lower())
        if signature in seen_signatures:
            attempts += 1
            continue

        exercises.append(prompt)
        seen_signatures.add(signature)
        attempts = 0

    return exercises


def generate_exercises_for_categories(
    categories: Sequence[str],
    quantity: int,
    difficulty: str = "beginner",
    category_weights: Optional[Dict[str, float]] = None,
) -> List[ExercisePrompt]:
    normalized = normalize_difficulty(difficulty)
    exercises: List[ExercisePrompt] = []

    available_specs = [
        spec for spec in GENERATOR_REGISTRY
        if spec.category in categories and normalized in spec.difficulties
    ]
    if not available_specs:
        available_specs = [spec for spec in GENERATOR_REGISTRY if spec.category in categories]
    if not available_specs:
        return generate_default_exercises(quantity, difficulty=normalized)

    specs_by_category: Dict[str, List[GeneratorSpec]] = {}
    for spec in available_specs:
        specs_by_category.setdefault(spec.category, []).append(spec)

    weighted_categories = list(specs_by_category.keys())
    weights = []
    for category in weighted_categories:
        weight = 1.0
        if category_weights:
            weight = max(0.1, float(category_weights.get(category, 1.0)))
        weights.append(weight)

    seen_signatures = set()
    attempts = 0
    max_attempts = max(10, quantity * 12)

    while len(exercises) < quantity and attempts < max_attempts:
        selected_category = random.choices(weighted_categories, weights=weights, k=1)[0]
        custom_prompt = _random_custom_item(selected_category, normalized)
        if custom_prompt and random.random() < 0.7:
            prompt = custom_prompt
        else:
            spec = random.choice(specs_by_category[selected_category])
            prompt = spec.builder(normalized)
        signature = (prompt.category, prompt.prompt.strip().lower())
        if signature in seen_signatures:
            attempts += 1
            continue
        exercises.append(prompt)
        seen_signatures.add(signature)
        attempts = 0

    if len(exercises) < quantity:
        exercises.extend(generate_default_exercises(quantity - len(exercises), difficulty=normalized))

    return exercises
