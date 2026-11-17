"""Conservative task matching and explicit identity ambiguity detection."""
import re
import unicodedata


def key(value):
    return ' '.join(''.join(c for c in unicodedata.normalize('NFD', value.casefold()) if not unicodedata.combining(c)).split())


def named_people(text, user_name):
    first = user_name.strip().split()[0]
    names = re.findall(r'\b(?i:' + re.escape(first) + r')\s+[A-ZÁÉÍÓÚÑ][a-záéíóúñ]+(?:\s+[A-ZÁÉÍÓÚÑ][a-záéíóúñ]+)?', text)
    excluded = {'preparara','enviara','revisara','entregara','remitira','elaborara'}
    return sorted({n for n in names if key(n.split()[1]) not in excluded})


def identities(text, user_name):
    names = named_people(text, user_name)
    return names if len({key(n) for n in names}) > 1 else []


def signature(description):
    aliases = {'entregar':'enviar', 'remitir':'enviar', 'mandar':'enviar', 'enviara':'enviar',
               'entregara':'enviar', 'remitira':'enviar', 'elaborar':'preparar', 'redactar':'preparar',
               'preparara':'preparar', 'elaborara':'preparar', 'revisara':'revisar', 'comprobar':'revisar'}
    stop = set('el la los las un una de del al a para por con y se su sus en que debera debe tiene encarga encargo'.split())
    words = [aliases.get(w, w) for w in re.findall(r'\w+', key(description)) if w not in stop]
    return words


def supports_task(description, evidence):
    """Reject a real quote used to justify an unrelated action or object."""
    def unclitic(word):
        for ending in ('las','los','les','la','lo','le'):
            base = word[:-len(ending)]
            if word.endswith(ending) and base.endswith(('ar','er','ir')):
                return base
        return word
    words = [unclitic(word) for word in signature(description)]
    source = {unclitic(word) for word in signature(evidence)}
    if not words:
        return False
    action = words[0]
    groups = ({'agregar','anadir','incorporar'}, {'preparar','elaborar','redactar'},
              {'enviar','remitir','entregar','mandar'}, {'revisar','comprobar'})
    aliases = next((group for group in groups if action in group), {action})
    if action.endswith(('ar','er','ir')):
        forms = {form for verb in aliases for form in (verb, verb+'a', verb[:-1])}
        if not forms & source:
            return False
        objects = set(words[1:])
    else:
        objects = set(words)
    objects -= set('tambien ademas ahora luego finalmente antes despues hoy manana lunes martes miercoles jueves viernes sabado domingo'.split())
    if not objects:
        return bool(source & aliases)
    if any(word.isdigit() and word not in source for word in objects):
        return False
    required = 1 if len(objects) <= 2 else .6
    return len(objects & source) / len(objects) >= required


def same_task(first, second):
    if key(first['responsable']) != key(second['responsable']):
        return False
    dates = [re.sub(r'^el\s+', '', key(t.get('fecha_limite') or '')) for t in (first, second)]
    if all(dates) and dates[0] != dates[1]:
        return False
    a, b = signature(first['descripcion']), signature(second['descripcion'])
    if not a or not b or a[0] != b[0]:
        return False
    # Keep different actions, objects and numbered deliverables separate.
    objects_a, objects_b = set(a[1:]), set(b[1:])
    return bool(objects_a) and objects_a == objects_b


def deduplicate(tasks):
    result = []
    for task in tasks:
        match = next((item for item in result if same_task(item, task)), None)
        quote = {'texto': task['evidencia'], 'inicio': task.get('inicio'), 'fin': task.get('fin')}
        if match:
            if quote not in match['evidencias']:
                match['evidencias'].append(quote)
            if not match.get('fecha_limite'):
                match['fecha_limite'] = task.get('fecha_limite')
        else:
            result.append({**task, 'evidencias': [quote]})
    return result
