#!/usr/bin/env python3
"""
Atom Swarm Dispatcher — runs Larry's 7 seed atoms on every user prompt.
Hook: UserPromptSubmit → reads JSON stdin → dispatches active atoms → returns systemMessage.

Usage: echo '{"user_prompt":"...","session_id":"..."}' | python3 atom_swarm.py
"""
import json, sys, os, re, random, math
from _paths import kernel_dir

# State в папке ядра владельца (writeable), не в read-only кэше плагина.
_STATE_DIR = str(kernel_dir() / ".claude" / "lenin")
os.makedirs(_STATE_DIR, exist_ok=True)

ATOMS_DIR = os.path.join(os.path.dirname(__file__), 'atoms')  # bundled atom prompts (optional)
SWARM_STATE_FILE = '/tmp/lenin_atom_swarm.json'
DYNAMIC_ATOMS_FILE = os.path.join(_STATE_DIR, 'dynamic_atoms.json')
FEP_STATE_FILE = '/tmp/lenin_fep_prediction.json'
MOMENTUM_FILE = os.path.join(_STATE_DIR, 'atom_momentum.json')
TRAJECTORY_FILE = '/tmp/lenin_trajectory.json'
POSTERIOR_CACHE = os.path.join(_STATE_DIR, 'posterior_cache.json')  # единый путь с unified_posterior

# Atom → card directory mapping for context loading
ATOM_CARD_MAP = {
    'therapist': {
        'dirs': ['library/patients/'],
        'pattern': ['p_', 'MASTER_DOSSIER_'],
        'label': 'Пациенты',
    },
    'entrepreneur': {
        'dirs': ['library/projects/', 'library/people/'],
        'pattern': ['biz_', 'MASTER_DOSSIER_'],
        'label': 'Проекты и партнёры',
    },
    'builder': {
        'dirs': ['library/projects/'],
        'pattern': ['biz_'],
        'label': 'Бизнес-проекты',
    },
    'synthesist': {
        'dirs': ['library/formal/'],
        'pattern': ['pedagogical_bridge', 'python/full_training'],
        'label': 'Формализация',
    },
}

# Atom config: (name, threshold, enabled, baseline=True → always on)
# Calibrated 2026-06-01: binary search on 136 transcripts, target 30% activation
STATIC_ATOM_CONFIG = {
    'curiosity':    {'threshold': 0.36, 'enabled': True,  'baseline': True,  'dims': ['I','L','G','M']},
    'memory':       {'threshold': 0.56, 'enabled': True,  'baseline': True,  'dims': ['C','M','S','E']},
    'state':        {'threshold': 0.15, 'enabled': True,  'baseline': False, 'dims': ['T','Ph','N','X']},
    'gap-architect':{'threshold': 0.41, 'enabled': True,  'baseline': False, 'dims': ['R','P','A','N']},
    'verifier':     {'threshold': 0.20, 'enabled': True,  'baseline': True,  'dims': ['C','N','R']},
    'forecaster':   {'threshold': 0.47, 'enabled': True,  'baseline': False, 'dims': ['A','P','E','T']},
    'self':         {'threshold': 0.34, 'enabled': True,  'baseline': False, 'dims': ['M','G','X','I'],
                     'schedule': 10},  # Konayev ext #5: activate every 10th prompt
    # ─── Profile atoms (v3, 2026-05-28, calibrated v5 2026-06-01 empirical) ───
    'therapist':    {'threshold': 0.45, 'enabled': True,  'baseline': False, 'dims': ['S','E','P','N']},
    'pedagogue':    {'threshold': 0.47, 'enabled': True,  'baseline': False, 'dims': ['L','G','M','C']},
    'builder':      {'threshold': 0.66, 'enabled': True,  'baseline': False, 'dims': ['M','A','P','T']},
    'entrepreneur': {'threshold': 0.42, 'enabled': True,  'baseline': False, 'dims': ['P','A','R','G']},
    'synthesist':   {'threshold': 0.36, 'enabled': True,  'baseline': False, 'dims': ['M','I','X','S']},
}

# Merged config: static + dynamic (loaded at runtime)
ATOM_CONFIG = dict(STATIC_ATOM_CONFIG)

# ─── Mutual exclusion groups (v4, 2026-05-30) ───
# Atoms in the same group compete: only the one with highest confidence activates.
# Groups defined by overlapping dims / semantic similarity.
EXCLUSION_GROUPS = [
    ['builder', 'entrepreneur'],    # both high A,P — implementation vs business reality
    ['curiosity', 'synthesist'],    # both high M,I — questioning vs connecting
    ['pedagogue', 'memory'],        # both high C,M — teaching vs recalling patterns
]

# Minimum confidence to appear in output (calibrated from 0.4)
CONFIDENCE_THRESHOLD = 0.3

# Quick 14D signal detection from text
# v5 (2026-06-01): balanced ~14 keywords per dim, expanded dead dims for business/conversational context
SIGNALS = {
    'E': ['эмоци', 'чувств', 'любов', 'страх', 'тревог', 'обид', 'радость',
          'грусть', 'счасть', 'нежн', 'злость', 'восторг', 'печал', 'волнен',
          'беспоко', 'нервнич', 'пережива', 'терп', 'злится', 'обидел'],
    'C': ['когнитив', 'памят', 'анали', 'логик', 'стратег', 'пониман',
          'осознан', 'рефлекси', 'вниман', 'рассужд', 'мышлен',
          'дум', 'считаю', 'предполага', 'вывод', 'оценк', 'мнени'],
    'S': ['социальн', 'общени', 'отношен', 'семь', 'друг', 'коллег',
          'конфликт', 'партнер', 'семья', 'близки', 'окружен',
          'вместе', 'между нами', 'доверя', 'поддержк', 'одиночеств'],
    'P': ['психолог', 'личност', 'характер', 'мотивац', 'ценност',
          'самооценк', 'идентичн', 'эго', 'темперамент', 'архетип',
          'тип', 'психотип', 'интроверт', 'экстраверт', 'поведени'],
    'Ph': [' тел', 'сон', 'здоров', 'стресс', 'пульс',
           'давлени', 'устал', 'вынослив', 'аппетит', 'энергия',
           'выгор', 'перегруз', 'отдых', 'нерв', 'расслаб', 'напряжен',
           'усталост', 'бодр', 'сонлив', 'тонус', 'физиче'],
    'T': ['творчеств', ' иде', 'проектиров', 'дизайн', 'креатив',
          'визуал', 'художеств', 'эстетик',
          'придума', 'концепц', 'подход', 'вариант', 'новый', 'оригинал'],
    'X': ['сексуальн', 'интимн', 'привлекательн', 'близость',
          'влечени', 'желани', 'романти', 'чувствен',
          'зачем', 'смысл жизни', 'смерт', 'одиночество', 'вера', 'надежд',
          'предательств', 'потеря', 'тоска', 'пустот', 'кризис смысл'],
    'N': ['нейро', 'мозг', 'дофамин', 'серотонин', 'кортизол',
          'нейромедиатор', 'синапс', 'пластичност', 'рецептор',
          'фокус', 'концентрац', 'внимательн', 'реакц', 'привычк',
          'автомат', 'навязчив', 'компульс', 'ритм', 'цикл'],
    'A': ['адаптац', 'изменени', 'кризис', 'гибкост', 'coping',
          'действи', 'шаг', 'сдела', 'реализ', 'выполн', 'запуск',
          'поступ', 'провел', 'написа', 'создал', 'построил', 'завершил'],
    'R': ['регуляц', 'контрол', 'управлен', 'правил', 'границ',
          'дисциплин', 'закон', 'налог', 'штраф', 'иск', 'суд',
          'порядок', 'ответствен', 'обязан', 'режим', 'норматив'],
    'I': ['исследован', 'гипотез', 'данны', 'метрик', 'валид',
          'эксперимент', 'выборк', 'корреляц', 'статистик', 'реплика',
          'анализ', 'цифр', 'тест', 'провер', 'результат', 'факт', 'доказател'],
    'L': ['обучени', 'навык', 'опыт', 'практик', 'курс', 'образован',
          'выучил', 'освоил', 'понял', 'разобрал', 'изучал',
          'трениров', 'упражнен', 'привычк', 'наработал'],
    'M': ['модел', 'систем', 'структур', 'алгоритм', 'формал',
          'математ', 'формул', 'уравнен', 'параметр', 'аппроксим'],
    'G': ['цель', 'результат', 'успех', 'план', 'приоритет', 'фокус',
          'смысл', 'достижен', 'прогресс', 'улучш', 'стратегич',
          'динамик', 'прирост', 'скорост', 'масштаб', 'карьер', 'компетенц'],
}

# TF-IDF weights: rare keywords get higher score, common keywords get lower.
# Computed from corpus: IDF = log(N / df) where df = docs containing keyword.
# Dim-level IDF: dims with few keywords (X, Ph, I, N, T) get boosted.
DIM_IDF_BOOST = {
    'E': 1.0, 'C': 1.0, 'S': 1.2, 'P': 0.7,
    'Ph': 4.0,  # was dead → max boost
    'T': 3.5,   # was dead → strong boost
    'X': 5.0,   # was deadest → max boost
    'M': 0.4,   # dominant → dampen hard
    'N': 4.0,   # was dead → max boost
    'A': 1.0, 'R': 1.2,
    'I': 4.0,   # was dead → max boost
    'L': 1.5, 'G': 1.5,
}

def quick_score(text):
    """Quick signal detection per dimension with IDF weighting."""
    tl = text.lower()
    signals = {}
    for dim, keywords in SIGNALS.items():
        count = 0
        for kw in keywords:
            n = tl.count(kw)
            if n > 0 and kw.strip() in (' тел', ' иде'):
                import re
                if kw.strip() == 'тел':
                    n = len(re.findall(r'\bтел[оауеиымя]?\b', tl))
                elif kw.strip() == 'иде':
                    n = len(re.findall(r'\bиде[яиюйемх]?\b', tl))
            count += n
        # Apply IDF boost: rare dims get amplified, dominant dims dampened
        signals[dim] = count * DIM_IDF_BOOST.get(dim, 1.0)
    return signals


# ─── Stylistic analysis layer (v3, 2026-05-28) ───
# Goes beyond keywords: analyzes HOW the user communicates.
# Detects self-reference, hedging, question depth, psychotype markers.

STYLE_PATTERNS = {
    'self_reference': {
        'patterns': [r'\bя\b', r'\bменя\b', r'\bмне\b', r'\bмой\b', r'\bмоя\b',
                     r'\bмоё\b', r'\bмои\b', r'\bмной\b', r'\bмы\b', r'\bнас\b',
                     r'\bнам\b', r'\bнаш\b'],
        'dims': {'P': 0.5, 'M': 0.3},  # psychotype self-focus + metacognition
        'label': 'self-ref',
    },
    'hedging': {
        'patterns': [r'\bкак бы\b', r'\bну вот\b', r'\bтам\b', r'\bнапример\b',
                     r'\bто есть\b', r'\bтипа\b', r'\bдопустим\b', r'\bскажем\b',
                     r'\bнаверное\b', r'\bвозможно\b', r'\bпожалуй\b', r'\bвроде\b',
                     r'\bкажется\b', r'\bпоходу\b', r'\bскорее всего\b'],
        'dims': {'M': 0.4, 'E': 0.3},  # metacognition (thinking aloud) + emotional regulation
        'label': 'hedging',
    },
    'exploratory': {
        'patterns': [r'\bкак ты\b', r'\bчто ты\b', r'\bпочему ты\b', r'\bчто если\b',
                     r'\bинтересно ли\b', r'\bкак думаешь\b', r'\bа если\b',
                     r'\bможет быть\b', r'\bли он\b', r'\bли она\b', r'\bли это\b'],
        'dims': {'M': 0.5, 'C': 0.3},  # metacognition + cognitive exploration
        'label': 'exploratory',
    },
    'imperative': {
        'patterns': [r'\bсделай\b', r'\bдавай\b', r'\bпродолжай\b', r'\bвыполни\b',
                     r'\bпроверь\b', r'\bпокажи\b', r'\bнапиши\b', r'\bзапусти\b',
                     r'\bсобери\b', r'\bзакоммить\b', r'\bобнови\b', r'\bисправь\b',
                     r'\bдобавь\b', r'\bнайди\b', r'\bчитает\b', r'\bчитай\b'],
        'dims': {'A': 0.6},  # agency, direct action
        'label': 'imperative',
    },
    'reformulation': {
        'patterns': [r'\bто есть\b', r'\bдругими словами\b', r'\bимею в виду\b',
                     r'\bв смысле\b', r'\bто есть я\b', r'\bвернее\b', r'\bточнее\b',
                     r'\bа именно\b'],
        'dims': {'C': 0.3, 'M': 0.3},  # cognitive clarification + metacognition
        'label': 'reform',
    },
    'psychotype_markers': {
        'patterns': [r'\bпсихотип\b', r'\bтемперамент\b', r'\bхарактер\b',
                     r'\bстиль\b', r'\bпаттерн\b', r'\bповедени\b', r'\bреакци\b',
                     r'\bмотив\b', r'\bархетип\b', r'\bтип личност\b',
                     r'\bинтроверт\b', r'\bэкстраверт\b', r'\bэмоциональн\b'],
        'dims': {'P': 0.7, 'N': 0.2},  # psychotype + neuro-cognitive
        'label': 'psych',
    },
    'emotional_undertone': {
        'patterns': [r'\bблин\b', r'\bчёрт\b', r'\bбоже\b', r'\bкстати\b',
                     r'\bладно\b', r'\bхорошо\b', r'\bнормально\b', r'\bприкольно\b',
                     r'\bстрашно\b', r'\bбеспокоит\b', r'\bбесит\b', r'\bрад\b'],
        'dims': {'E': 0.5},  # emotional
        'label': 'emotion',
    },
    'connective_density': {
        'patterns': [r'\bпотому что\b', r'\bпоэтому\b', r'\bзначит\b', r'\bв итоге\b',
                     r'\bследовательно\b', r'\bтаким образом\b', r'\bс одной сторон\b',
                     r'\bс другой сторон\b', r'\bпри этом\b', r'\bхотя\b',
                     r'\bоднако\b', r'\bнесмотря на\b'],
        'dims': {'C': 0.4},  # cognitive complexity
        'label': 'connect',
    },
    'system_reflection': {
        'patterns': [r'\bядро\b', r'\bсистема\b', r'\bработает\b', r'\bподключает\b',
                     r'\bмодель\b', r'\bалгоритм\b', r'\bpipeline\b', r'\bhook\b',
                     r'\bпостериор\b', r'\bвеса\b', r'\bрой\b', r'\bатомы\b',
                     r'\bформализация\b', r'\bобучен\b'],
        'dims': {'M': 0.4, 'N': 0.2},  # metacognition (system-aware) + neuro-modeling
        'label': 'sys-ref',
    },
    # ─── Profile-specific style patterns (v3, 2026-05-28) ───
    'therapist_lang': {
        'patterns': [r'\bтрансфер\b', r'\bконтрперенос\b', r'\bсопротивлен\b', r'\bконтейнирован\b',
                     r'\bтерапи\b', r'\bпациент\b', r'\bклиент\b', r'\bсесси\b',
                     r'\bдиагноз\b', r'\bрасстройств\b', r'\bтревожн\b', r'\bдепресси\b',
                     r'\bаддикц\b', r'\bзависимост\b', r'\bтравм\b', r'\bпривязанност\b',
                     r'\bэмпати\b', r'\bраппорт\b', r'\bабьюз\b', r'\bграниц[ыье]',
                     r'\bмикродоз\b', r'\bpsilocyb\b', r'\bплакал\b', r'\bслёз\b',
                     r'\bспасти\b', r'\bспасат\b', r'\bмам[аоуые]\b', r'\bпап[аоуые]\b',
                     r'\bкокаин\b', r'\bалкогол\b', r'\bнарко\b', r'\bзапой\b'],
        'dims': {'S': 0.4, 'E': 0.3},  # social dynamics + emotional attunement
        'label': 'therapist',
    },
    'pedagogue_lang': {
        'patterns': [r'\bобучени\b', r'\bнаучит\b', r'\bобъясн\b', r'\bпониман\b',
                     r'\bзона ближайшего\b', r'\bscaffolding\b', r'\bнаставник\b',
                     r'\bментор\b', r'\bпедагог\b', r'\bучител\b', r'\bкак научить\b',
                     r'\bкак объяснить\b', r'\bпрозрачн\b', r'\bglass box\b',
                     r'\bосвоил\b', r'\bнавык\b', r'\bкомпетенц\b'],
        'dims': {'L': 0.4, 'G': 0.3},  # learning + growth
        'label': 'pedagogue',
    },
    'builder_lang': {
        'patterns': [r'\bархитектур\b', r'\bмодул\b', r'\bAPI\b', r'\bфреймворк\b',
                     r'\bSwift\b', r'\biOS\b', r'\bmacOS\b', r'\bvisionOS\b',
                     r'\bcode\b', r'\bbuild\b', r'\bреализаци\b', r'\bинтерфейс\b',
                     r'\bбэкенд\b', r'\bфронтенд\b', r'\bбаз[аеу]\b', r'\bдепло\b',
                     r'\bпротокол\b', r'\bструктур\b', r'\bкомпонент\b', r'\bвиджет\b',
                     r'\bSwiftUI\b', r'\bXcode\b', r'\bMVP\b', r'\bпрод\b'],
        'dims': {'M': 0.3, 'A': 0.4},  # models + action/implementation
        'label': 'builder',
    },
    'entrepreneur_lang': {
        'patterns': [r'\bбюджет\b', r'\bденьги\b', r'\bприбыл\b', r'\bROI\b',
                     r'\bмасштаб\b', r'\bвыручк\b', r'\bинвести\b', r'\bрынок\b',
                     r'\bконкурент\b', r'\bпартнёр\b', r'\bдоговор\b', r'\bмиллион\b',
                     r'\bмлн\b', r'\bмлрд\b', r'\bKPI\b', r'\bметрик\b',
                     r'\bворонк\b', r'\bконверси\b', r'\bлид\b', r'\bклиент\b',
                     r'\bподрядчик\b', r'\bкоманд\b', r'\bнайм\b', r'\bфинанс\b',
                     r'\balignment\b', r'\bдоля\b', r'\bакци\b', r'\bдивиденд\b',
                     r'\bкэш\b', r'\bburn rate\b', r'\brunway\b'],
        'dims': {'P': 0.4, 'R': 0.3},  # projects + regulation/risk
        'label': 'biz',
    },
    'synthesist_lang': {
        'patterns': [r'\bсвязь\b', r'\bаналог\b', r'\bпохоже на\b', r'\bтак же как\b',
                     r'\bпараллел\b', r'\bмост\b', r'\bbridge\b', r'\bинтегрир\b',
                     r'\bкросс\b', r'\bмежд\[аоуы]\b', r'\bсинтез\b', r'\bобъедин',
                     r'\bобщее\b', r'\bв пересечени\b', r'\bс одной сторон.*с другой\b',
                     r'\bкак.*так и\b', r'\bи то и другое\b',
                     r'\bодин и тот же\b', r'\bодна и та же\b', r'\bразных масштаб\b',
                     r'\bкак.*и.*одновременно\b', r'\bпересечени\b', r'\bформализ'],
        'dims': {'M': 0.3, 'I': 0.3},  # metacognition + insight/cross-domain
        'label': 'synth',
    },
    # ─── Cognitive distortions (ABC/B = belief layer, from CBT) ───
    'catastrophizing': {
        'patterns': [r'\bвсё\b.*\bплохо\b', r'\bконец\b', r'\bвсё потерян\b',
                     r'\bникогда не\b', r'\bничего не\b', r'\bвсё пропал\b',
                     r'\bужасно\b', r'\bкатастроф\b', r'\bэто конец\b',
                     r'\bвсё рухнет\b', r'\bне выжив\b', r'\bразвалится\b',
                     r'\bхудше\b.*\bбывает\b', r'\bчто дальше\b.*\bплох\b',
                     r'\bне справлюсь\b', r'\bне выдержу\b', r'\bвсё закончится\b'],
        'dims': {'E': 0.6, 'T': -0.3, 'X': 0.2},  # emotion high, therapy low, existential
        'distortion': 'catastrophizing',
        'label': 'catastr',
    },
    'mind_reading': {
        'patterns': [r'\bон думает\b', r'\bона думает\b', r'\bони считают\b',
                     r'\bточно знает\b', r'\bон хочет\b.*\bмне\b', r'\bона считает\b',
                     r'\bдумает что я\b', r'\bвсе считают\b', r'\bникто не считает\b',
                     r'\bему всё равн\b', r'\bона не понимает\b', r'\bон не хочет\b',
                     r'\bони против\b', r'\bему нужн\b.*\bтолько\b', r'\bона использует\b'],
        'dims': {'S': 0.5, 'C': -0.2},  # social high, cognition low (assumption without evidence)
        'distortion': 'mind_reading',
        'label': 'mindread',
    },
    'all_or_nothing': {
        'patterns': [r'\bили\b.*\bили\b', r'\bвсегда\b', r'\bникогда\b',
                     r'\bвсе\b', r'\bникто\b', r'\bничего\b', r'\bвсё\b',
                     r'\bполностью\b', r'\bабсолютно\b', r'\bсовершенно\b',
                     r'\bтолько так\b', r'\bиначе никак\b', r'\bлибо\b.*\bлибо\b',
                     r'\bидеальн\b', r'\bбездарн\b', r'\bгениальн\b.*\bужасн\b'],
        'dims': {'C': 0.4, 'A': -0.2},  # cognitive rigidity, agency low (no middle ground)
        'distortion': 'all_or_nothing',
        'label': 'allornothing',
    },
    'emotional_reasoning': {
        'patterns': [r'\bчувствую значит\b', r'\bзнаю сердцем\b', r'\bнутром чувствую\b',
                     r'\bкажется значит\b', r'\bбоюсь значит\b.*\bопасно\b',
                     r'\bне могу\b.*\bпотому что\b.*\bчувств\b',
                     r'\bсердце подсказывает\b', r'\bинтуиция говорит\b',
                     r'\bпочему-то\b.*\bплох\b', r'\bне по себе\b',
                     r'\bтревожно значит\b', r'\bвнутренний голос\b'],
        'dims': {'E': 0.5, 'R': -0.2},  # emotion high, regulation low
        'distortion': 'emotional_reasoning',
        'label': 'emotreas',
    },
    'should_statements': {
        'patterns': [r'\bдолжен\b', r'\bобязан\b', r'\bнельзя\b', r'\bнадо\b',
                     r'\bнужно\b.*\bобязательно\b', r'\bдолжна\b', r'\bобязана\b',
                     r'\bположено\b', r'\bкак надо\b', r'\bкак следует\b',
                     r'\bнедопустимо\b', r'\bне имею прав\b', r'\bне могу позволить\b',
                     r'\bобязател\b.*\bиначе\b', r'\bвсегда должен\b'],
        'dims': {'A': 0.5, 'X': -0.2},  # agency high (external), existential low (no freedom)
        'distortion': 'should_statements',
        'label': 'should',
    },
    'personalization': {
        'patterns': [r'\bиз-за меня\b', r'\bэто я\b.*\bвиноват\b', r'\bмоя вина\b',
                     r'\bя\b.*\bиспортил\b', r'\bвсе\b.*\bиз-за меня\b',
                     r'\bя подвёл\b', r'\bопять я\b', r'\bкак всегда я\b',
                     r'\bбез меня бы\b', r'\bмоя ошибка\b.*\bвсе\b',
                     r'\bя\b.*\bответствен\b.*\bза\b'],
        'dims': {'E': 0.3, 'S': 0.3, 'X': 0.2},  # emotional + social guilt + existential
        'distortion': 'personalization',
        'label': 'personal',
    },
}


def style_score(text):
    """Stylistic analysis: detects HOW the user communicates, not just WHAT.

    Returns:
        style_signals: dict of {dim: float} — fractional hits per dimension
        style_report: list of (pattern_name, count, label) for diagnostics
    """
    tl = text.lower()
    style_signals = {}
    style_report = []

    for pattern_name, cfg in STYLE_PATTERNS.items():
        count = 0
        for pat in cfg['patterns']:
            found = len(re.findall(pat, tl))
            count += found
        if count > 0:
            for dim, weight in cfg['dims'].items():
                style_signals[dim] = style_signals.get(dim, 0) + count * weight
            style_report.append((pattern_name, count, cfg['label']))

    return style_signals, style_report


# ── Belief Layer (ABC model: B = beliefs between A and C) ──

# Belief templates: regex → (belief_type, affected_dims, distortion_if_any)
BELIEF_TEMPLATES = [
    # Self-worth beliefs
    (r'\bя не\s*(?:могу|умею|способен|достоин|заслуживаю|смогу)\b', 'self_doubt',
     {'A': -0.3, 'E': 0.2, 'X': 0.2}, None),
    (r'\bя всегда\b|\bя никогда\b|\bопять я\b', 'self_pattern',
     {'M': 0.3, 'E': 0.2}, 'personalization'),
    (r'\bмне не\s*(?:хватит|дано|под силу|по зубам)\b', 'self_limiting',
     {'A': -0.3, 'G': -0.2}, None),
    # Control beliefs
    (r'\bничего не\s*(?:зависит|изменится|поможет)\b', 'helplessness',
     {'A': -0.4, 'T': -0.2}, 'catastrophizing'),
    (r'\bвсё\s*(?:потеряно|плохо|ужасно|конец)\b', 'catastrophic_belief',
     {'E': 0.4, 'X': 0.2}, 'catastrophizing'),
    (r'\bдолжен\b.*\bиначе\b|\bобязан\b.*\bили\b', 'rigid_rule',
     {'A': 0.3, 'X': -0.2}, 'should_statements'),
    # Relational beliefs
    (r'\bон[аи]?\s*(?:не понимает|против|не хочет|использует|бросит)\b', 'other_negative',
     {'S': 0.4, 'R': -0.2}, 'mind_reading'),
    (r'\bвсе\s*(?:против|бросят|предадут|обманут)\b', 'universal_distrust',
     {'S': 0.3, 'E': 0.3, 'R': -0.3}, 'mind_reading'),
    # Growth beliefs (positive)
    (r'\bя могу\b|\bя смогу\b|\bя справлюсь\b|\bполучится\b|\bполучается\b|\bнайду способ\b', 'self_efficacy',
     {'A': 0.4, 'G': 0.3}, None),
    (r'\bучусь\b|\bучиться\b|\bстановится лучше\b|\bстановлюсь\b|\bпрогресс\b|\bрасту\b|\bрастёт\b', 'growth_belief',
     {'G': 0.4, 'M': 0.2}, None),
    (r'\bпринимаю\b|\bмне достаточно\b|\bя выбираю\b', 'acceptance_belief',
     {'X': 0.3, 'R': 0.2}, None),
]


def extract_beliefs(text: str) -> list[dict]:
    """Extract implicit beliefs from text (ABC model: B layer).

    Returns list of {type, dims, distortion, confidence} dicts.
    This sits between A (signals) and C (atoms), modeling what the user BELIEVES
    rather than just what they SAID.

    Negative dims (e.g. A: -0.3) mean the belief suppresses that dimension.
    Positive dims mean the belief activates that dimension.
    """
    tl = text.lower()
    beliefs = []

    for pattern, belief_type, dims, distortion in BELIEF_TEMPLATES:
        matches = re.findall(pattern, tl)
        if matches:
            confidence = min(1.0, len(matches) / 3.0)
            beliefs.append({
                'type': belief_type,
                'dims': dims,
                'distortion': distortion,
                'confidence': round(confidence, 2),
                'count': len(matches),
            })

    return beliefs


def belief_signals(beliefs: list[dict]) -> dict:
    """Convert extracted beliefs to dim signals for fusion.

    Beliefs modify the signal landscape: a 'helplessness' belief suppresses A,
    making agency-related atoms less likely to activate (the user feels stuck,
    not agentic). A 'self_efficacy' belief boosts A and G.
    """
    signals = {}
    for b in beliefs:
        for dim, weight in b.get('dims', {}).items():
            current = signals.get(dim, 0.0)
            signals[dim] = current + weight * b.get('confidence', 0.5)
    return signals


# Fusion weights calibrated 2026-06-01 on 136 transcripts
# Style layer (HOW user speaks) contributes 67% of signal vs keywords 33%
FUSION_WEIGHTS = {'keywords': 0.33, 'style': 0.67, 'belief': 0.00}


def combined_score(text):
    """Merge keyword signals + stylistic analysis + belief layer into unified scores.

    Calibrated v5 (2026-06-01):
    - Fusion: keywords 33%, style 67%, belief 0%
    - Normalized per 1000 chars to remove length bias
    """
    chars = max(len(text), 1)
    norm_factor = 1000.0 / chars

    kw_signals = quick_score(text)
    st_signals, style_report = style_score(text)
    beliefs = extract_beliefs(text)
    bel_signals = belief_signals(beliefs)

    fw = FUSION_WEIGHTS
    merged = {}
    for d in SIGNALS.keys():
        kw = kw_signals.get(d, 0) * fw['keywords']
        st = st_signals.get(d, 0) * fw['style']
        bl = bel_signals.get(d, 0) * fw['belief']
        merged[d] = (kw + st + bl) * norm_factor

    return merged, style_report, beliefs


# ─── Dynamic atom system (nursery + miner) ───

DIMS_LIST = ["E", "C", "S", "P", "Ph", "T", "X", "M", "N", "A", "R", "I", "L", "G"]

def _load_dynamic_atoms() -> dict:
    """Load dynamic atoms from nursery file, merge into ATOM_CONFIG."""
    global ATOM_CONFIG
    if not os.path.exists(DYNAMIC_ATOMS_FILE):
        return {}
    try:
        data = json.loads(open(DYNAMIC_ATOMS_FILE, encoding='utf-8').read())
        dynamic = data.get('atoms', {})
        for name, cfg in dynamic.items():
            if name not in STATIC_ATOM_CONFIG:
                ATOM_CONFIG[name] = cfg
        return dynamic
    except (json.JSONDecodeError, OSError):
        return {}


def _save_dynamic_atoms(data: dict) -> None:
    """Persist dynamic atoms."""
    tmp = DYNAMIC_ATOMS_FILE + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, DYNAMIC_ATOMS_FILE)


def _get_dim_coverage() -> dict[str, float]:
    """How many atoms cover each dimension."""
    coverage = {d: 0.0 for d in DIMS_LIST}
    for cfg in ATOM_CONFIG.values():
        for d in cfg.get('dims', []):
            coverage[d] = coverage.get(d, 0) + 1
    return coverage


def mine_atoms_from_history(min_occurrences: int = 5) -> list[dict]:
    """Mine new atom candidates from signal_history.

    Algorithm:
      1. Load signal_history from posterior_cache.json
      2. For each event, compute dim_hits profile
      3. Cluster events by dim similarity (cosine > 0.7)
      4. Clusters that don't match existing atoms → new candidate
      5. Only propose if cluster appears ≥ min_occurrences times
    """
    # Load history
    cache_path = POSTERIOR_CACHE
    if not os.path.exists(cache_path):
        return []
    try:
        cache = json.loads(open(cache_path, encoding='utf-8').read())
    except (json.JSONDecodeError, OSError):
        return []

    history = cache.get('signal_history', [])
    swarm_events = [h for h in history if h.get('source') == 'atom_swarm' and h.get('dim_hits')]
    if len(swarm_events) < min_occurrences:
        return []

    # Normalize each event's dim_hits to a profile
    profiles = []
    for evt in swarm_events[-100:]:  # last 100 events
        hits = evt.get('dim_hits', {})
        total = sum(hits.values()) if isinstance(hits, dict) else 0
        if total == 0:
            continue
        profile = {d: hits.get(d, 0) / total for d in DIMS_LIST}
        profiles.append(profile)

    if len(profiles) < min_occurrences:
        return []

    # Simple clustering: find dim pairs/groups that co-occur above chance
    cooccurrence = {(d1, d2): 0.0 for d1 in DIMS_LIST for d2 in DIMS_LIST}
    for p in profiles:
        for d1 in DIMS_LIST:
            for d2 in DIMS_LIST:
                cooccurrence[(d1, d2)] += p.get(d1, 0) * p.get(d2, 0)
    n = len(profiles)
    for k in cooccurrence:
        cooccurrence[k] /= n

    # Extract clusters: dims that are strongly correlated (>0.1 co-variance)
    candidates = []
    used_dims = set()
    for d1 in DIMS_LIST:
        if d1 in used_dims:
            continue
        cluster = [d1]
        for d2 in DIMS_LIST:
            if d2 != d1 and d2 not in used_dims:
                if cooccurrence.get((d1, d2), 0) > 0.08:
                    cluster.append(d2)
        if len(cluster) >= 2:
            # Check if this cluster is already covered by an existing atom
            covered = False
            for cfg in ATOM_CONFIG.values():
                atom_dims = set(cfg.get('dims', []))
                if set(cluster).issubset(atom_dims):
                    covered = True
                    break
                overlap = len(set(cluster) & atom_dims) / len(cluster)
                if overlap > 0.75:
                    covered = True
                    break

            if not covered:
                # Count how many profiles have this cluster active
                count = 0
                for p in profiles:
                    cluster_signal = sum(p.get(d, 0) for d in cluster)
                    total_signal = sum(p.values())
                    if total_signal > 0 and cluster_signal / total_signal > 0.3:
                        count += 1

                if count >= min_occurrences:
                    candidates.append({
                        'dims': cluster[:4],  # max 4 dims per atom
                        'occurrences': count,
                        'strength': round(count / n, 3),
                    })
                    used_dims.update(cluster)

    # Load existing dynamic atoms to avoid re-proposing
    dynamic_data = {}
    if os.path.exists(DYNAMIC_ATOMS_FILE):
        try:
            dynamic_data = json.loads(open(DYNAMIC_ATOMS_FILE, encoding='utf-8').read())
        except Exception:
            pass
    existing_dynamic = set(dynamic_data.get('atoms', {}).keys())

    # Name and create new atoms
    new_atoms = []
    for i, cand in enumerate(candidates):
        dims = cand['dims']
        name = f"dyn_{'_'.join(d[:2].lower() for d in dims)}_{i+1}"
        if name in existing_dynamic or name in STATIC_ATOM_CONFIG:
            continue

        atom_def = {
            'threshold': 0.30,  # high threshold for seedlings
            'enabled': True,
            'baseline': False,
            'dims': dims,
            'status': 'seedling',  # seedling → validated → mature
            'activations': 0,
            'created_from': 'miner',
            'occurrences': cand['occurrences'],
            'strength': cand['strength'],
        }
        new_atoms.append({'name': name, 'config': atom_def})
        ATOM_CONFIG[name] = atom_def

    # Persist
    if new_atoms:
        atoms_store = dynamic_data.get('atoms', {})
        for na in new_atoms:
            atoms_store[na['name']] = na['config']
        _save_dynamic_atoms({
            'version': '1.0',
            'updated': __import__('datetime').datetime.now().isoformat(),
            'atoms': atoms_store,
        })

    return new_atoms


def promote_dynamic_atom(atom_name: str) -> bool:
    """Promote a seedling atom after sufficient activations.

    seedling (≥5 activations) → validated (threshold lowered)
    validated (≥20 activations) → mature (can't be auto-pruned)
    """
    if not os.path.exists(DYNAMIC_ATOMS_FILE):
        return False
    try:
        data = json.loads(open(DYNAMIC_ATOMS_FILE, encoding='utf-8').read())
    except Exception:
        return False

    atom = data.get('atoms', {}).get(atom_name)
    if not atom:
        return False

    n_act = atom.get('activations', 0) + 1
    atom['activations'] = n_act

    if atom.get('status') == 'seedling' and n_act >= 5:
        atom['status'] = 'validated'
        atom['threshold'] = round(atom.get('threshold', 0.30) * 0.75, 3)
    elif atom.get('status') == 'validated' and n_act >= 20:
        atom['status'] = 'mature'
        atom['threshold'] = round(max(0.15, atom.get('threshold', 0.22) * 0.85), 3)

    ATOM_CONFIG[atom_name] = atom
    _save_dynamic_atoms(data)
    return True


def prune_stale_dynamic_atoms(max_age_days: int = 30, min_activations: int = 3) -> list[str]:
    """Remove dynamic atoms that never activated."""
    if not os.path.exists(DYNAMIC_ATOMS_FILE):
        return []
    try:
        data = json.loads(open(DYNAMIC_ATOMS_FILE, encoding='utf-8').read())
    except Exception:
        return []

    pruned = []
    atoms = data.get('atoms', {})
    to_keep = {}
    for name, atom in atoms.items():
        if atom.get('status') == 'mature':
            to_keep[name] = atom
            continue
        if atom.get('activations', 0) >= min_activations:
            to_keep[name] = atom
            continue
        pruned.append(name)

    if pruned:
        data['atoms'] = to_keep
        _save_dynamic_atoms(data)
        # Remove from runtime config
        for name in pruned:
            ATOM_CONFIG.pop(name, None)

    return pruned


# ─── Automatic FEP loop (predict → observe → update) ───

def _fep_check_previous(actual_dims: dict) -> dict | None:
    """Check if there was a pending prediction and compare with actual."""
    if not os.path.exists(FEP_STATE_FILE):
        return None
    try:
        pred = json.loads(open(FEP_STATE_FILE, encoding='utf-8').read())
    except (json.JSONDecodeError, OSError):
        return None

    # Compare predicted top dims with actual
    pred_top3 = set(sorted(pred.get('predicted_dims', {}), key=lambda d: -pred['predicted_dims'].get(d, 0))[:3])
    actual_top3 = set(sorted(actual_dims, key=lambda d: -actual_dims.get(d, 0))[:3])
    overlap = len(pred_top3 & actual_top3)

    # Cosine similarity between predicted and actual
    import math
    dims = list(actual_dims.keys())
    pred_v = [pred.get('predicted_dims', {}).get(d, 0) for d in dims]
    act_v = [actual_dims.get(d, 0) for d in dims]
    dot = sum(a * b for a, b in zip(pred_v, act_v))
    mag_p = math.sqrt(sum(v ** 2 for v in pred_v))
    mag_a = math.sqrt(sum(v ** 2 for v in act_v))
    cosine = dot / (mag_p * mag_a) if mag_p * mag_a > 0 else 0

    error = 1.0 - cosine  # FEP error: 0=perfect, 1=completely wrong

    result = {
        'predicted': pred_top3,
        'actual': actual_top3,
        'overlap': overlap,
        'cosine': round(cosine, 4),
        'error': round(error, 4),
        'predicted_atoms': pred.get('predicted_atoms', []),
        'prompt_preview': pred.get('prompt_preview', ''),
    }

    # Write to unified posterior FEP
    try:
        _hooks_dir = os.path.dirname(os.path.abspath(__file__))
        if _hooks_dir not in sys.path:
            sys.path.insert(0, _hooks_dir)
        from unified_posterior import UnifiedPosterior
        up = UnifiedPosterior()
        up.update_from_fep(
            prediction=f"top_dims={pred_top3} atoms={pred.get('predicted_atoms', [])}",
            actual=f"top_dims={actual_top3} cosine={cosine:.3f}",
            error=error,
            atom=pred.get('predicted_atoms', [''])[0] if pred.get('predicted_atoms') else None,
        )
    except Exception:
        pass

    return result


def _fep_make_prediction(dims: dict, atoms: list[str], text_preview: str) -> None:
    """Store prediction for next prompt to check against."""
    pred = {
        'predicted_dims': {d: round(v, 4) for d, v in dims.items() if v > 0},
        'predicted_atoms': atoms,
        'prompt_preview': text_preview[:100],
        'ts': __import__('datetime').datetime.now().isoformat(),
    }
    with open(FEP_STATE_FILE, 'w', encoding='utf-8') as f:
        json.dump(pred, f, ensure_ascii=False)


def get_atom_cards(atom_names: list[str], root: str = '') -> dict[str, list[str]]:
    """Get relevant card paths for activated atoms."""
    if not root:
        root = os.path.dirname(os.path.abspath(__file__))
        root = os.path.normpath(os.path.join(root, '..', '..'))
    result = {}
    for atom in atom_names:
        if atom not in ATOM_CARD_MAP:
            continue
        cfg = ATOM_CARD_MAP[atom]
        cards = []
        for d in cfg['dirs']:
            full_dir = os.path.join(root, d)
            if not os.path.exists(full_dir):
                continue
            for f in os.listdir(full_dir):
                if any(pat in f for pat in cfg['pattern']):
                    cards.append(os.path.join(d, f))
        if cards:
            result[atom] = sorted(cards)[:5]  # max 5 cards per atom
    return result


def load_atom_prompt(name):
    """Load system prompt for an atom."""
    path = os.path.join(ATOMS_DIR, name, 'system-prompt.md')
    if os.path.exists(path):
        with open(path, 'r', encoding='utf-8') as f:
            return f.read()
    return None

# ─── Living cognition layer (v4, 2026-05-30) ───
# Atom momentum + emotional trajectory + multi-signal fusion

def _load_momentum() -> dict:
    """Load atom momentum history: each atom's recent confidence scores."""
    if not os.path.exists(MOMENTUM_FILE):
        return {}
    try:
        return json.loads(open(MOMENTUM_FILE, encoding='utf-8').read())
    except Exception:
        return {}


def _save_momentum(data: dict) -> None:
    """Persist momentum state."""
    tmp = MOMENTUM_FILE + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False)
    os.replace(tmp, MOMENTUM_FILE)


def update_momentum(active_atoms: list[tuple[str, float]]) -> None:
    """Update momentum after each dispatch.

    Active atoms get their confidence appended to history.
    Inactive atoms get a 0 appended (they're cooling down).
    History capped at last 10 activations per atom.
    """
    momentum = _load_momentum()
    active_names = {n for n, _ in active_atoms}

    for name in ATOM_CONFIG:
        if name not in momentum:
            momentum[name] = []

        if name in active_names:
            conf = next((c for n, c in active_atoms if n == name), 0.0)
            momentum[name].append(conf)
        else:
            momentum[name].append(0.0)

        momentum[name] = momentum[name][-10:]  # keep last 10

    _save_momentum(momentum)


def get_atom_momentum(atom_name: str) -> float:
    """Compute momentum score for an atom (0-1).

    Recent activations weighted more. High recent confidence = hot atom.
    Decay: older activations contribute less. Like a real skill that warms up.
    """
    momentum = _load_momentum()
    history = momentum.get(atom_name, [])
    if not history:
        return 0.0

    # Exponential decay: last activation weight=1.0, previous=0.7, etc.
    weights = [0.7 ** i for i in range(len(history))]
    weights.reverse()  # most recent last, so reverse for correct weighting

    total = sum(w * c for w, c in zip(weights, history))
    max_possible = sum(weights)

    return round(total / max_possible, 3) if max_possible > 0 else 0.0


# ── Transition matrix from empirical chunk-level calibration (3258 chunks, 17512 transitions) ──
# P(next_atom | prev_atom) from real therapy + business transcripts.
# Key insight: atoms PERSIST (self-transitions 8-27%), unlike the old
# hardcoded matrix which had 0% self-transitions.

CLINICAL_TRANSITIONS = {
    'curiosity':    {'curiosity': 0.216, 'builder': 0.134, 'therapist': 0.13, 'memory': 0.111,
                     'forecaster': 0.109, 'gap-architect': 0.096, 'self': 0.06, 'verifier': 0.054,
                     'pedagogue': 0.042, 'synthesist': 0.027, 'entrepreneur': 0.015, 'state': 0.006},
    'memory':       {'memory': 0.247, 'therapist': 0.136, 'builder': 0.133, 'forecaster': 0.112,
                     'curiosity': 0.093, 'gap-architect': 0.091, 'self': 0.052, 'verifier': 0.051,
                     'synthesist': 0.036, 'pedagogue': 0.029, 'entrepreneur': 0.014, 'state': 0.005},
    'state':        {'builder': 0.144, 'therapist': 0.115, 'curiosity': 0.108, 'memory': 0.099,
                     'gap-architect': 0.087, 'forecaster': 0.087, 'self': 0.085, 'state': 0.076,
                     'verifier': 0.074, 'pedagogue': 0.071, 'synthesist': 0.034, 'entrepreneur': 0.019},
    'gap-architect':{'gap-architect': 0.216, 'builder': 0.133, 'therapist': 0.131, 'memory': 0.113,
                     'forecaster': 0.113, 'curiosity': 0.096, 'verifier': 0.058, 'self': 0.049,
                     'pedagogue': 0.039, 'synthesist': 0.03, 'entrepreneur': 0.017, 'state': 0.005},
    'verifier':     {'verifier': 0.169, 'therapist': 0.129, 'builder': 0.126, 'memory': 0.114,
                     'gap-architect': 0.1, 'curiosity': 0.097, 'forecaster': 0.096, 'self': 0.056,
                     'pedagogue': 0.048, 'synthesist': 0.029, 'entrepreneur': 0.028, 'state': 0.009},
    'forecaster':   {'forecaster': 0.238, 'therapist': 0.135, 'builder': 0.135, 'memory': 0.12,
                     'curiosity': 0.098, 'gap-architect': 0.097, 'self': 0.051, 'verifier': 0.047,
                     'pedagogue': 0.031, 'synthesist': 0.031, 'entrepreneur': 0.013, 'state': 0.005},
    'self':         {'self': 0.158, 'builder': 0.136, 'therapist': 0.129, 'curiosity': 0.111,
                     'memory': 0.111, 'forecaster': 0.102, 'gap-architect': 0.092, 'verifier': 0.057,
                     'pedagogue': 0.048, 'synthesist': 0.033, 'entrepreneur': 0.016, 'state': 0.007},
    'therapist':    {'therapist': 0.268, 'builder': 0.131, 'memory': 0.117, 'forecaster': 0.11,
                     'curiosity': 0.095, 'gap-architect': 0.093, 'self': 0.051, 'verifier': 0.05,
                     'synthesist': 0.034, 'pedagogue': 0.033, 'entrepreneur': 0.013, 'state': 0.005},
    'pedagogue':    {'pedagogue': 0.136, 'builder': 0.135, 'therapist': 0.122, 'curiosity': 0.118,
                     'gap-architect': 0.105, 'forecaster': 0.097, 'memory': 0.094, 'verifier': 0.073,
                     'self': 0.066, 'entrepreneur': 0.022, 'synthesist': 0.022, 'state': 0.01},
    'builder':      {'builder': 0.268, 'therapist': 0.13, 'memory': 0.114, 'forecaster': 0.109,
                     'curiosity': 0.098, 'gap-architect': 0.092, 'self': 0.054, 'verifier': 0.051,
                     'pedagogue': 0.036, 'synthesist': 0.031, 'entrepreneur': 0.011, 'state': 0.006},
    'entrepreneur': {'therapist': 0.127, 'gap-architect': 0.115, 'builder': 0.114, 'memory': 0.111,
                     'entrepreneur': 0.099, 'curiosity': 0.097, 'forecaster': 0.097, 'verifier': 0.093,
                     'self': 0.055, 'pedagogue': 0.052, 'synthesist': 0.03, 'state': 0.01},
    'synthesist':   {'therapist': 0.15, 'builder': 0.145, 'memory': 0.137, 'synthesist': 0.12,
                     'forecaster': 0.11, 'gap-architect': 0.09, 'curiosity': 0.085, 'self': 0.057,
                     'verifier': 0.053, 'pedagogue': 0.032, 'entrepreneur': 0.013, 'state': 0.007},
}

def get_transition_bonus(atom_name: str) -> float:
    """Transition probability from last active atom to this one.

    Based on 342 clinical transcripts: how does a real therapist
    naturally shift perspectives? Returns 0-0.3 bonus.

    If curiosity was active last and this is state → 0.22 × 0.3 = 0.066 bonus.
    If curiosity was active last and this is gap-architect → 0.06 × 0.3 = 0.018 bonus.
    State/self get ~3.6× more transition bonus than gap-architect — matching real therapy.
    """
    momentum = _load_momentum()

    # Find the most recently active atom (highest recent score)
    best_prev = None
    best_score = 0.0
    for name, history in momentum.items():
        if history and history[-1] > best_score:
            best_score = history[-1]
            best_prev = name

    if best_prev is None or best_prev == atom_name:
        return 0.0

    transitions = CLINICAL_TRANSITIONS.get(best_prev, {})
    prob = transitions.get(atom_name, 0.0)

    # Scale to 0-0.3 range (transition is supplementary signal, not primary)
    return round(prob * 0.3, 3)


def _load_trajectory() -> list[dict]:
    """Load dimensional trajectory: E,C,S... values for last N prompts."""
    if not os.path.exists(TRAJECTORY_FILE):
        return []
    try:
        return json.loads(open(TRAJECTORY_FILE, encoding='utf-8').read())
    except Exception:
        return []


def _save_trajectory(data: list[dict]) -> None:
    """Persist trajectory (keep last 20)."""
    tmp = TRAJECTORY_FILE + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(data[-20:], f, ensure_ascii=False)
    os.replace(tmp, TRAJECTORY_FILE)


def update_trajectory(signals: dict) -> dict:
    """Append current signal snapshot to trajectory. Returns trajectory summary.

    Returns dict with:
      - e_trend: 'rising'|'stable'|'falling' — emotional trajectory
      - dominant_shift: 'to_emotional'|'to_analytical'|'stable' — where conversation is heading
      - velocity: dict of per-dim velocity (last 3 vs previous 3)
    """
    trajectory = _load_trajectory()
    trajectory.append(signals)
    trajectory = trajectory[-20:]
    _save_trajectory(trajectory)

    if len(trajectory) < 3:
        return {'e_trend': 'stable', 'dominant_shift': 'stable', 'velocity': {}}

    # Compute velocity: compare recent window vs previous window
    recent = trajectory[-3:]
    previous = trajectory[-6:-3] if len(trajectory) >= 6 else trajectory[:3]

    velocity = {}
    for dim in ['E', 'C', 'S', 'P', 'Ph', 'T', 'X', 'M', 'N', 'A', 'R', 'I', 'L', 'G']:
        recent_avg = sum(r.get(dim, 0) for r in recent) / len(recent)
        prev_avg = sum(r.get(dim, 0) for r in previous) / len(previous)
        velocity[dim] = round(recent_avg - prev_avg, 3)

    # Emotional trajectory
    e_vel = velocity.get('E', 0)
    if e_vel > 0.5:
        e_trend = 'rising'
    elif e_vel < -0.5:
        e_trend = 'falling'
    else:
        e_trend = 'stable'

    # Dominant shift: emotional dims vs analytical dims
    emotional_vel = velocity.get('E', 0) + velocity.get('S', 0) + velocity.get('Ph', 0)
    analytical_vel = velocity.get('C', 0) + velocity.get('M', 0) + velocity.get('N', 0)

    if emotional_vel > analytical_vel + 0.5:
        dominant_shift = 'to_emotional'
    elif analytical_vel > emotional_vel + 0.5:
        dominant_shift = 'to_analytical'
    else:
        dominant_shift = 'stable'

    return {'e_trend': e_trend, 'dominant_shift': dominant_shift, 'velocity': velocity}


def _trajectory_bonus(atom_name: str, trajectory: dict) -> float:
    """Bonus for atoms aligned with conversation trajectory.

    Human intuition: if emotions are rising, empathy-related atoms should activate more easily.
    If conversation is becoming analytical, logic atoms should gain.
    """
    dims = ATOM_CONFIG.get(atom_name, {}).get('dims', [])
    velocity = trajectory.get('velocity', {})
    e_trend = trajectory.get('e_trend', 'stable')
    dominant_shift = trajectory.get('dominant_shift', 'stable')

    bonus = 0.0

    # Direct dim velocity: if atom's dims are trending up, boost
    dim_vel = sum(velocity.get(d, 0) for d in dims) / max(len(dims), 1)
    bonus += dim_vel * 0.1  # subtle: trajectory adds 10% of velocity

    # Emotional priority: if E is rising, boost emotion-sensitive atoms
    if e_trend == 'rising' and atom_name in ('therapist', 'state'):
        bonus += 0.15  # human: when emotions rise, attend to them first
    elif e_trend == 'falling' and atom_name in ('verifier', 'gap-architect'):
        bonus += 0.1   # human: when emotions settle, analysis becomes possible

    # Dominant shift: boost atoms matching conversation direction
    if dominant_shift == 'to_emotional' and atom_name in ('therapist', 'state', 'memory'):
        bonus += 0.1
    elif dominant_shift == 'to_analytical' and atom_name in ('verifier', 'builder', 'entrepreneur'):
        bonus += 0.1

    return round(min(bonus, 0.3), 3)  # cap at 0.3 to prevent runaway


def _apply_uptake_adj(thresholds):
    """Промоушен uptake в поведение: help_rate линзы сдвигает её порог.
    Мягко, клампы [0.15,0.85], baseline не трогаем. Обратимо (удалить json = откат)."""
    try:
        adj_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'uptake_threshold_adj.json')
        if not os.path.exists(adj_path):
            return thresholds
        adj = json.load(open(adj_path, encoding='utf-8')).get('adjustments', {})
        out = dict(thresholds)
        for atom, delta in adj.items():
            if atom in out:
                out[atom] = max(0.15, min(0.85, out[atom] + delta))
        return out
    except Exception:
        return thresholds

def _load_calibrated_thresholds():
    """Load calibrated thresholds from unified posterior, then apply uptake adjustment."""
    base = None
    try:
        _hooks_dir = os.path.dirname(os.path.abspath(__file__))
        if _hooks_dir not in sys.path:
            sys.path.insert(0, _hooks_dir)
        from unified_posterior import UnifiedPosterior
        up = UnifiedPosterior()
        calibrated = up.get_atom_thresholds()
        if calibrated and len(calibrated) == len(ATOM_CONFIG):
            base = calibrated
    except Exception:
        pass
    if base is None:
        base = {name: cfg['threshold'] for name, cfg in ATOM_CONFIG.items()}
    return _apply_uptake_adj(base)


def should_activate(atom_name, signals, style_signals, text_len,
                    thresholds=None, prompt_count=0, trajectory=None):
    """Compute atom activation confidence via multi-signal fusion.

    Fuses 4 signals:
      1. keyword_signal — keyword matches in atom's dims (what is said)
      2. style_signal — stylistic pattern matches (how it's said)
      3. momentum_signal — atom's recent activation history (is it "warmed up")
      4. trajectory_signal — conversation direction bonus (where it's heading)

    Returns confidence 0-1. Baseline atoms get 1.0. Scheduled atoms get 0.8.
    """
    if thresholds is None:
        thresholds = _load_calibrated_thresholds()
    if trajectory is None:
        trajectory = {}
    cfg = ATOM_CONFIG.get(atom_name, {})
    if not cfg.get('enabled', True):
        return 0.0

    # ── Scheduled atoms ──
    schedule = cfg.get('schedule', 0)
    if schedule > 0:
        if prompt_count > 0 and prompt_count % schedule == 0:
            return 0.8
        return 0.0

    # ── Baseline atoms: always on ──
    if cfg.get('baseline', False) and text_len >= 15:
        return 1.0

    atom_dims = cfg.get('dims', [])

    # ── Signal 1: Keywords (WHAT is said) ──
    total_kw = sum(signals.get(d, 0) for d in atom_dims)
    if text_len < 50:
        kw_intensity = total_kw / 5.0
    elif text_len < 500:
        kw_intensity = total_kw / (text_len / 100.0)
    else:
        effective_len = 100.0 * math.sqrt(text_len / 100.0)
        kw_intensity = total_kw / effective_len
    kw_score = min(1.0, kw_intensity * 2)

    # ── Signal 2: Style (HOW it's said) ──
    style_total = sum(style_signals.get(d, 0) for d in atom_dims)
    # Style is more subtle: normalize differently
    style_score = min(1.0, style_total / 3.0) if style_total > 0 else 0.0

    # ── Signal 3: Momentum (is the atom "warmed up"?) ──
    momentum = get_atom_momentum(atom_name)
    # Momentum acts as a multiplier: hot atom needs less keyword signal
    momentum_score = momentum * 0.5  # cap momentum contribution

    # ── Signal 4: Trajectory (where is conversation heading?) ──
    traj_bonus = _trajectory_bonus(atom_name, trajectory)

    # ── Signal 5: Clinical transition (how does a real therapist shift?) ──
    transition_bonus = get_transition_bonus(atom_name)

    # ── Fusion: weighted combination ──
    # Keywords (45%), style (22%), momentum (13%), trajectory (10%), clinical transition (10%)
    fused = (
        0.45 * kw_score +
        0.22 * style_score +
        0.13 * momentum_score +
        0.10 * traj_bonus +
        0.10 * transition_bonus
    )

    # Clamp to 0-1
    fused = round(min(1.0, max(0.0, fused)), 3)

    threshold = thresholds.get(atom_name, cfg.get('threshold', 0.5))
    if fused >= threshold:
        margin = (fused - threshold) / (1.0 - threshold) if threshold < 1.0 else 0.0
        return round(0.4 + 0.6 * margin, 3)
    return 0.0

def extract_hits(text, keywords):
    """Extract which keywords actually hit, with surrounding context."""
    tl = text.lower()
    hits = []
    for kw in keywords:
        idx = tl.find(kw)
        if idx >= 0:
            start = max(0, idx - 20)
            end = min(len(text), idx + len(kw) + 20)
            fragment = text[start:end].strip()
            if start > 0:
                fragment = "..." + fragment
            if end < len(text):
                fragment = fragment + "..."
            hits.append((kw, fragment))
    return hits

def dispatch(text):
    """Detect active atoms via multi-signal fusion with confidence and mutual exclusion."""
    signals, style_report, beliefs = combined_score(text)
    # Extract raw style signals (per-dim weights from style patterns)
    style_signals_raw, _ = style_score(text)
    text_len = len(text)

    # Get prompt count for scheduled atoms
    prompt_count = 0
    try:
        _hooks_dir = os.path.dirname(os.path.abspath(__file__))
        cache_path = POSTERIOR_CACHE
        if os.path.exists(cache_path):
            cache = json.loads(open(cache_path, encoding='utf-8').read())
            prompt_count = cache.get('calibration', {}).get('n_prompts_processed', 0) + 1
    except Exception:
        pass

    # Compute conversation trajectory
    trajectory = update_trajectory(signals)

    # Adaptive dimensionality: cap active atoms by text length
    # With 15 atoms total: tier 1=3, tier 2=5, tier 3=7
    if text_len < 50:
        max_atoms = 3
    elif text_len < 500:
        max_atoms = 5
    else:
        max_atoms = 7

    # Step 1: Compute confidence for every atom via multi-signal fusion
    scored_atoms = []
    thresholds = _load_calibrated_thresholds()
    for name, cfg in ATOM_CONFIG.items():
        conf = should_activate(name, signals, style_signals_raw, text_len,
                               thresholds, prompt_count, trajectory)
        if conf > 0:
            scored_atoms.append((name, conf))

    # ── Konayev ext #4: Random atom activation ──
    # 10% chance to add a random non-active atom
    if random.random() < 0.10 and text_len > 50:
        active_names = {n for n, _ in scored_atoms}
        inactive = [n for n in ATOM_CONFIG
                    if n not in active_names
                    and ATOM_CONFIG[n].get('enabled', True)
                    and not ATOM_CONFIG[n].get('baseline', False)
                    and not ATOM_CONFIG[n].get('schedule', 0)]
        if inactive:
            chosen = random.choice(inactive)
            scored_atoms.append((chosen, 0.35))  # low confidence = marked as random

    # Step 2: Apply confidence threshold — filter out noise
    scored_atoms = [(n, c) for n, c in scored_atoms if c >= CONFIDENCE_THRESHOLD]

    # Step 3: Apply mutual exclusion groups
    # For each group, keep only the atom with highest confidence
    excluded = set()
    for group in EXCLUSION_GROUPS:
        group_scored = [(n, c) for n, c in scored_atoms if n in group]
        if len(group_scored) > 1:
            # Sort by confidence descending, keep winner
            group_scored.sort(key=lambda x: x[1], reverse=True)
            winner = group_scored[0][0]
            for n, _ in group_scored[1:]:
                excluded.add(n)

    scored_atoms = [(n, c) for n, c in scored_atoms if n not in excluded]

    # Step 4: Sort by confidence, apply tier cap
    scored_atoms.sort(key=lambda x: x[1], reverse=True)
    scored_atoms = scored_atoms[:max_atoms]

    if not scored_atoms:
        return None

    # Step 5: Update atom momentum (for next prompt's fusion)
    update_momentum(scored_atoms)

    active_atoms = [n for n, _ in scored_atoms]
    confidence_map = {n: c for n, c in scored_atoms}

    atom_data = []
    for atom_name in active_atoms:
        cfg = ATOM_CONFIG[atom_name]
        atom_dims = cfg.get('dims', [])

        all_hits = []
        for d in atom_dims:
            hits = extract_hits(text, SIGNALS.get(d, []))
            for kw, frag in hits:
                all_hits.append((d, kw, frag))

        seen_kw = set()
        unique = []
        for dim, kw, frag in all_hits:
            if kw not in seen_kw:
                seen_kw.add(kw)
                unique.append((dim, kw, frag))

        fragments = [frag for _, _, frag in unique[:3]]
        keywords = [kw for _, kw, _ in unique[:3]]

        atom_data.append({
            'name': atom_name,
            'keywords': keywords,
            'fragments': fragments,
            'is_baseline': cfg.get('baseline', False) and text_len >= 15,
            'confidence': confidence_map[atom_name],
        })

    return atom_data

def main():
    try:
        # Load dynamic atoms from nursery
        _load_dynamic_atoms()

        # Periodically mine new atoms (every 50th prompt)
        try:
            _hooks_dir = os.path.dirname(os.path.abspath(__file__))
            cache_path = POSTERIOR_CACHE
            if os.path.exists(cache_path):
                cache = json.loads(open(cache_path, encoding='utf-8').read())
                n_prompts = cache.get('calibration', {}).get('n_prompts_processed', 0)
                if n_prompts > 0 and n_prompts % 50 == 0:
                    mine_atoms_from_history()
                    prune_stale_dynamic_atoms()
        except Exception:
            pass

        # Read hook input
        input_data = {}
        if not sys.stdin.isatty():
            raw = sys.stdin.read()
            if raw.strip():
                input_data = json.loads(raw)

        # Extract user message
        user_text = ''
        if 'user_prompt' in input_data:
            user_text = input_data['user_prompt']
        elif 'message' in input_data:
            msg = input_data['message']
            if isinstance(msg, dict):
                content = msg.get('content', '')
                if isinstance(content, list):
                    user_text = ' '.join(c.get('text', '') for c in content if isinstance(c, dict))
                else:
                    user_text = str(content)
            else:
                user_text = str(msg)

        if not user_text or len(user_text.strip()) < 10:
            # Too short to analyze
            print(json.dumps({"continue": True}))
            return

        # Dispatch atoms + combined scoring (keyword + stylistic)
        main_signals, style_report, beliefs = combined_score(user_text)
        atom_data = dispatch(user_text)

        # FEP: check previous prediction, make new one
        fep_result = _fep_check_previous(main_signals)

        if atom_data:
            atom_names = [a['name'] for a in atom_data]

            # Promote dynamic atoms that activated
            for name in atom_names:
                cfg = ATOM_CONFIG.get(name, {})
                if cfg.get('status') in ('seedling', 'validated'):
                    promote_dynamic_atom(name)

            # Build raw signal lines for additionalContext
            signal_lines = []
            for a in atom_data:
                parts = [a['name']]
                conf = a.get('confidence', 0.5)
                if conf < 1.0:
                    parts.append(f'conf={conf:.2f}')
                if a['is_baseline']:
                    parts.append('baseline')
                if a['keywords']:
                    parts.append('keywords: ' + ', '.join(a['keywords']))
                if a['fragments']:
                    parts.append('context: «' + a['fragments'][0] + '»')
                signal_lines.append(' | '.join(parts))

            raw_signal = '\n'.join(signal_lines)

            # Build style report line if any stylistic patterns detected
            style_line = ''
            if style_report:
                style_parts = [f'{label}×{count}' for _, count, label in style_report]
                style_line = f"Style: {' · '.join(style_parts)}\n"
            analytical_score = main_signals.get('I', 0) + main_signals.get('M', 0)
            emotional_score = main_signals.get('E', 0) + main_signals.get('Ph', 0)
            # ST recommended when analytical signals dominate
            st_recommended = analytical_score > 0 and analytical_score >= emotional_score

            state = {
                'atoms': atom_names,
                'signal_lines': signal_lines,
                'prompt_len': len(user_text),
                'st_recommended': st_recommended,
                'tier': 1 if len(user_text) < 50 else (2 if len(user_text) < 500 else 3),
                'n_active': len(atom_names),
            }
            with open(SWARM_STATE_FILE, 'w', encoding='utf-8') as f:
                json.dump(state, f, ensure_ascii=False)

            # Feed signal back to unified posterior
            try:
                _hooks_dir = os.path.dirname(os.path.abspath(__file__))
                if _hooks_dir not in sys.path:
                    sys.path.insert(0, _hooks_dir)
                from unified_posterior import UnifiedPosterior
                up = UnifiedPosterior()
                up.snapshot_posterior()  # save before-update for novelty
                up.update_from_swarm(main_signals, len(user_text), atom_names)
                # Konayev ext #2: domain-specific posterior
                domain = up._detect_domain(user_text)
                if domain:
                    scale = min(2.0, len(user_text) / 200.0) if len(user_text) > 0 else 0.5
                    dom_counts = {d: main_signals.get(d, 0) * scale for d in up.DIMS if hasattr(up, 'DIMS')}
                    if not dom_counts:
                        from unified_posterior import DIMS as UP_DIMS
                        dom_counts = {d: main_signals.get(d, 0) * scale for d in UP_DIMS}
                    up.update_domain_posterior(domain, dom_counts)
                # Konayev ext #1: semantic novelty
                novelty = up.semantic_novelty()
                novelty_label = up.novelty_label(novelty)
                cracks = up.detect_cracks()
                # v3: use blended posterior (long-term + session)
                state['posterior_14d'] = up.get_blended_posterior()
                state['session_posterior'] = up.get_session_posterior()
                state['session_info'] = up.get_session_info()
                state['semantic_novelty'] = novelty
                state['novelty_label'] = novelty_label
                state['domain'] = domain
                if cracks:
                    state['cracks'] = cracks
                with open(SWARM_STATE_FILE, 'w', encoding='utf-8') as f:
                    json.dump(state, f, ensure_ascii=False)
            except Exception:
                pass  # never block

            # Build FEP line
            fep_line = ''
            if fep_result:
                fep_line = (
                    f"FEP check: predicted {fep_result['predicted']} → "
                    f"actual {fep_result['actual']} "
                    f"(cos={fep_result['cosine']:.2f} err={fep_result['error']:.2f})\n"
                )

            # ── v4: Trajectory line (living cognition) ──
            traj = _load_trajectory()
            if len(traj) >= 3:
                e_trend = '↑' if sum(t.get('E', 0) for t in traj[-3:]) > sum(t.get('E', 0) for t in traj[-6:-3] if traj[-6:-3]) else '→'
                top_vel = sorted(
                    [(d, sum(t.get(d, 0) for t in traj[-3:]) - sum(t.get(d, 0) for t in (traj[-6:-3] or traj[:3])))
                     for d in DIMS_LIST],
                    key=lambda x: abs(x[1]), reverse=True
                )[:3]
                vel_str = ', '.join(f"{d}{'↑' if v > 0 else '↓'}" for d, v in top_vel)
                trajectory_line = f"Trajectory: E{e_trend} | velocity: {vel_str}\n"
            else:
                trajectory_line = ''

            # ── Konayev ext #3: N+1 verifier protocol ──
            n1_line = ''
            if 'verifier' in atom_names:
                n1_line = (
                    "N+1 verifier: for each factual claim, answer:\n"
                    "  1. What was achieved? (the claim itself)\n"
                    "  2. Why wasn't it known before? (what changed)\n"
                    "  3. Why exactly this source/observation? (specificity check)\n"
                )

            # ── Konayev ext #1: semantic novelty line ──
            novelty_val = state.get('semantic_novelty', 0)
            novelty_lbl = state.get('novelty_label', 'unknown')
            novelty_line = f"Semantic novelty: {novelty_val:.4f} ({novelty_lbl})\n"

            # ── Konayev ext #2: domain + cracks ──
            domain_line = ''
            detected_domain = state.get('domain')
            if detected_domain:
                domain_line = f"Domain: {detected_domain}\n"
            cracks = state.get('cracks', [])
            if cracks:
                crack_desc = '; '.join(c['interpretation'] for c in cracks[:3])
                domain_line += f"Cracks: {crack_desc}\n"

            # ── v4: Instrument + delivery + T-bridge + epistemic postures ──
            instrument_line = ''
            delivery_line = ''
            bridge_lines = ''
            posture_line = ''
            try:
                _hooks_dir = os.path.dirname(os.path.abspath(__file__))
                if _hooks_dir not in sys.path:
                    sys.path.insert(0, _hooks_dir)
                from instrument_selector import select_instruments, format_instrument_output
                from delivery_selector import select_delivery, format_delivery_hint
                from epistemic_postures import select_postures, format_posture_output

                # Get posterior weights for instrument/delivery selection
                post_14d = state.get('posterior_14d', {})
                weights_list = [post_14d.get(d, 1/14) for d in DIMS_LIST]

                instruments = select_instruments(
                    weights_list,
                    gradient_dims=None,
                    domain=detected_domain,
                    max_instruments=2,
                )
                instrument_line = format_instrument_output(instruments)

                delivery_form = select_delivery(post_14d if post_14d else {d: 1/14 for d in DIMS_LIST})
                delivery_line = format_delivery_hint(delivery_form)

                # Run T-bridges
                try:
                    from entropy_bridge import run_entropy_bridges
                    weights_prev = None  # TODO: pass previous weights from snapshot
                    bridge_results = run_entropy_bridges(
                        weights_list, weights_prev, active_atoms=atom_names
                    )
                    for r in bridge_results:
                        if r.get('recommendation'):
                            bridge_lines += f"[T-{r.get('theorem','?')}] {r['recommendation']}\n"
                except ImportError:
                    pass

                try:
                    from nonlinear_bridge import run_nonlinear_bridges
                    # Build weight history from posterior cache
                    weight_history = []
                    try:
                        cache_path_h = POSTERIOR_CACHE
                        if os.path.exists(cache_path_h):
                            cache_h = json.loads(open(cache_path_h, encoding='utf-8').read())
                            for evt in cache_h.get('signal_history', [])[-10:]:
                                if evt.get('dim_hits'):
                                    weight_history.append(list(evt['dim_hits'].values()))
                    except Exception:
                        pass
                    if weight_history:
                        nl_results = run_nonlinear_bridges(weight_history)
                        for r in nl_results:
                            if r.get('recommendation'):
                                bridge_lines += f"[T-{r.get('theorem','?')}] {r['recommendation']}\n"
                except ImportError:
                    pass

                # ── Epistemic postures (Коняев-derived) ──
                try:
                    postures = select_postures(atom_names, post_14d, max_postures=2)
                    posture_line = format_posture_output(postures)
                except Exception:
                    pass
            except ImportError:
                pass  # graceful degradation

            additional_ctx = (
                f"Atom swarm signal — {len(atom_names)} atoms active.\n"
                f"Active atoms with signal:\n{raw_signal}\n"
                f"{style_line}"
                f"{fep_line}"
                f"{trajectory_line}"
                f"{novelty_line}"
                f"{domain_line}"
                f"{n1_line}"
                f"{instrument_line}\n"
                f"{delivery_line}\n"
                f"{bridge_lines}"
                f"{posture_line}"
                f"Sequential-thinking: {'RECOMMENDED' if st_recommended else 'skip'}"
                f"{' (analytical atoms active)' if st_recommended else ' (conversational mode)'}\n"
                "Think through active atom lenses (atom-lenses.md). "
                "If an insight emerges, prefix response with: ── atoms: "
                + ' · '.join(atom_names) + " ──"
            )
            output = {
                "continue": True,
                "hookSpecificOutput": {
                    "hookEventName": "UserPromptSubmit",
                    "additionalContext": additional_ctx
                }
            }
            # FEP: store prediction for next prompt
            _fep_make_prediction(main_signals, atom_names, user_text)
        else:
            output = {"continue": True}

        print(json.dumps(output, ensure_ascii=False))

    except Exception as e:
        # Never block the main flow
        print(json.dumps({"continue": True}))

if __name__ == '__main__':
    main()
