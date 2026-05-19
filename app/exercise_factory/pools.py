"""Banques de vocabulaire et de phrases utilisées par les générateurs.

Toutes les données sont organisées par niveau (``beginner`` / ``intermediate``
/ ``advanced``). Les helpers ``_pooled_dict`` / ``_pooled_list`` cumulent
plusieurs niveaux successifs pour offrir plus de matière au niveau supérieur.
"""

from typing import Dict, List, Tuple


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
