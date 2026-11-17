"""Recover explicit named assignments while keeping literal source evidence.

These rules supplement the local model. Questions, hypotheses, completed work
and unclear subjects remain outside automatic assignment.
"""
import re

from task_matching import key, named_people, signature

ADVERBS = r"(?:(?:también|además|ahora|luego|después|finalmente|tambien|ademas|despues)\s*,?\s+){0,2}"
COMMITMENT = r"(?:va a|debe|deberá|debera|tiene que|se encarga de|se encargará de|se encargara de|se compromete a|se comprometió a|se comprometio a|queda encargado de|quedó encargado de|quedo encargado de)"
FUTURE = r"(?:\w+(?:ará|erá|irá)|preparara|enviara|remitira|revisara|realizara|redactara|desarrollara|elaborara|entregara|actualizara|analizara|escribira|creara|validara|probara|implementara|corregira|hara)"
PRESENT = {"prepara":"preparar", "envia":"enviar", "revisa":"revisar", "elabora":"elaborar",
           "entrega":"entregar", "agrega":"agregar", "actualiza":"actualizar", "redacta":"redactar"}
UNCERTAIN = re.compile(r"\b(?:quizas|quiza|tal vez|podria|podrias|puedes|deberia|supongamos|ojala|quiere|quisiera|desea|desearia)\b")
DATE = re.compile(r"\b(?:(?:para|antes del?|a mas tardar|hasta)\s+)?(?:el\s+)?(?:lunes|martes|miercoles|jueves|viernes|sabado|domingo|manana|hoy)\b|\b(?:para|antes del?|a mas tardar|hasta)\s+(?:el\s+)?\d{1,2}(?:\s+de\s+\w+|[/.-]\d{1,2}(?:[/.-]\d{2,4})?)?\b|\bel\s+\d{1,2}\s+de\s+\w+\b|\b\d{1,2}[/.-]\d{1,2}(?:[/.-]\d{2,4})?\b|\ba las\s+\d{1,2}(?::\d{2})?\b", re.I)


def sentences(text):
    return [part.strip() for part in re.split(r"(?<=[.!?;])\s+|\n+", text) if part.strip()]


def infinitive(verb):
    irregular = {"hara":"hacer", "pondra":"poner", "tendra":"tener", "dira":"decir", "saldra":"salir"}
    folded = key(verb)
    if folded in PRESENT:
        return PRESENT[folded]
    if folded in irregular:
        return irregular[folded]
    return verb[:-1] if folded.endswith(("ara", "era", "ira")) else verb


def coordinated_action(action):
    return re.sub(r"\by\s+(?P<pronoun>lo|la|los|las)\s+(?P<verb>" + FUTURE + r")\b",
                  lambda match: "y " + infinitive(match["verb"]) + match["pronoun"].lower(), action, flags=re.I)


def assignment(sentence, user):
    folded = key(sentence)
    if "?" in sentence or "¿" in sentence or UNCERTAIN.search(folded) or re.search(r"\bsi\b", sentence, re.I):
        return None
    names = [user] + named_people(sentence, user)
    subject = "|".join(re.escape(name) for name in sorted(set(names), key=len, reverse=True))
    match = re.search(r"(?<!\w)(?:" + subject + r")(?!\w)\s*[:,]?\s+" + ADVERBS + r"(?P<action>.+)", sentence, re.I)
    if not match:
        return None
    if re.search(r"\bno\b|\bsin confirmar\b|\bdescartamos\b", key(sentence[:match.start()])):
        return None
    action = match["action"].rstrip(".!?;").strip()
    if re.match(r"no\b|nunca\b|ya\b", key(action)):
        return None
    # A second named subject must not be folded into the first person's task.
    if re.search(r"\by\s+[A-ZÁÉÍÓÚÑ][\wáéíóúñ]+\s+(?:" + ADVERBS + COMMITMENT + "|" + FUTURE + r")\b", action):
        return None
    commitment = re.match(COMMITMENT + r"\s+(?P<body>.+)", action, re.I)
    if commitment:
        return coordinated_action(commitment["body"].strip())
    future = re.match(r"(?P<verb>" + FUTURE + r")\b(?P<body>.*)", action, re.I)
    if future and key(future["verb"]) not in {"sera", "estara", "podra", "llegara", "sabra"}:
        return coordinated_action(infinitive(future["verb"]) + future["body"])
    first, _, rest = action.partition(" ")
    # Present + explicit coordinated future: "prepara X y lo enviará".
    coordinated = re.search(r"\by\s+(?P<pronoun>lo|la|los|las)\s+(?P<verb>" + FUTURE + r")\b", rest, re.I)
    if key(first) in PRESENT and coordinated:
        return coordinated_action(PRESENT[key(first)] + " " + rest)
    return None


def literal_date(action):
    # Accent folding keeps character offsets for ordinary Spanish NFC text.
    match = DATE.search(key(action))
    if not match:
        return None
    # Return a source substring, never a reconstructed/calendar date.
    words = action.split()
    for start in range(len(words)):
        for end in range(start + 1, min(len(words), start + 9) + 1):
            candidate = " ".join(words[start:end]).strip(".,;:")
            if key(candidate) == match[0]:
                return candidate
    return None


def explicit_tasks(text, user):
    result = []
    for sentence in sentences(text):
        if len(sentence) > 2000:
            continue
        action = assignment(sentence, user)
        if not action or len(action) > 800:
            continue
        # Complex independent actions are left to the model; do not collapse
        # distinct deliverables into one task in the fallback.
        if re.search(r"\by\s+(?:" + FUTURE + r")\b", action, re.I):
            continue
        deadline = literal_date(action)
        description = action
        if deadline and action.endswith(deadline):
            description = action[:-len(deadline)].rstrip(" ,")
        result.append({"descripcion": description[:1].upper() + description[1:], "responsable": user,
                       "fecha_limite": deadline, "evidencia": sentence})
    return result


def supplement_tasks(candidates, doubtful, text, user):
    recovered = explicit_tasks(text, user)
    def replaced(item):
        quote = key(item["evidencia"]).rstrip('.!?;')
        words = signature(item["descripcion"])
        for task in recovered:
            rule_words = signature(task["descripcion"])
            if (key(item.get("responsable") or "") == key(user) and key(task["evidencia"]).rstrip('.!?;') in quote
                    and words and rule_words and words[0] == rule_words[0]):
                return True
        return False
    return [item for item in candidates if not replaced(item)] + recovered, [item for item in doubtful if not replaced(item)]


def upcoming_meetings(text):
    result = []
    for sentence in sentences(text):
        folded = key(sentence)
        if (len(sentence) <= 350 and not UNCERTAIN.search(folded) and "?" not in sentence and not re.search(r"\bsi\b", sentence, re.I)
                and re.search(r"\b(?:proxima|siguiente)\s+(?:reunion|sesion)\s+(?:sera|es|queda|se celebrara|se realizara)\b", folded)
                and not re.search(r"\bno\b", folded) and literal_date(sentence)):
            if sentence not in result:
                result.append(sentence)
    return result
