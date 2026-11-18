
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import csv
import hashlib
import json
import re
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
PDF = ROOT / 'Original_Dataset/PowerEdge Error Event Message Guide.pdf'
FIELDS = [
    ('message', r'^Message\s+(.*)$'),
    ('arguments', r'^Arguments\s*(.*)$'),
    ('explanation', r'^Detailed Description\s*(.*)$'),
    ('recommended_action', r'^Recommended(?: Response Action)?\s*(.*)$'),
    ('vendor_category', r'^Category\s+(.*)$'),
    ('severity', r'^Severity\s+(.*)$'),
    ('trap_event_id', r'^Trap/EventID\s*(.*)$'),
    ('lcd_message', r'^LCD Message\s*(.*)$'),
    ('redfish_event_type', r'^Redfish Event Type\s*(.*)$'),
    ('delivery_channels', r'^Applicable Event or\s*(.*)$'),
    ('omsa', r'^OMSA (?:Event|Trap) ID\s*(.*)$'),
]
CONTENT_FIELDS = ('message', 'explanation', 'recommended_action', 'arguments')
CODE = re.compile(r'[A-Z]{2,8}\d{1,6}')


def normalized(text):
    return re.sub(r'\s+', ' ', text.replace('\u00ad', '').replace('\xa0', ' ')).strip()


def save_json(path, obj):
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + '\n')


def pdf_text(mode):
    return subprocess.run(['pdftotext', '-' + mode, str(PDF), '-'],
                          check=True, capture_output=True, text=True).stdout


def extract():
    text = pdf_text('layout')
    pages = text.split('\f')
    if not pages[-1].strip():
        pages.pop()
    lines = []
    for page_number, page in enumerate(pages, 1):
        for line_number, raw in enumerate(page.splitlines(), 1):
            value = raw.strip()
            if not value or re.fullmatch(r'\d+', value):
                continue
            if 'PowerEdge Servers Error and Event Messages (EEMs)' in value:
                continue
            lines.append({'text': value, 'pdf_page': page_number,
                          'text_line': line_number, 'indent': len(raw)-len(raw.lstrip())})
    starts = []
    for i, line in enumerate(lines):
        if line['pdf_page'] < 10 or not CODE.fullmatch(line['text']):
            continue
        # An event heading must lead to its Message field, not merely mention a code.
        lookahead = lines[i+1:i+14]
        if any(re.match(r'^Message\s+', x['text']) and x['indent'] < 5 for x in lookahead):
            starts.append(i)
    entries, issues = [], []
    for number, start in enumerate(starts):
        end = starts[number+1] if number+1 < len(starts) else len(lines)
        fields = defaultdict(list)
        current = None
        for line in lines[start+1:end]:
            value = line['text']
            if re.match(r'^[A-Z]{2,8}[—–-].+Event Messages$', value):
                continue
            matched = False
            if line['indent'] < 5:
                for key, pattern in FIELDS:
                    match = re.match(pattern, value)
                    if match:
                        current, matched = key, True
                        if match[1]:
                            fields[key].append({**line, 'text': match[1]})
                        break
            if not matched and current:
                if current == 'recommended_action':
                    value = re.sub(r'^Response Action\s*', '', value)
                if current == 'delivery_channels':
                    value = re.sub(r'^Alert Types\s*', '', value)
                if value:
                    fields[current].append({**line, 'text': value})
        code = lines[start]['text']
        values = {k: normalized(' '.join(x['text'] for x in v)) for k, v in fields.items()}
        # Severity is a single enumerated value on its labelled source line.
        severity_lines = fields.get('severity', [])
        severity = severity_lines[0]['text'] if severity_lines else None
        if severity not in {'Critical', 'Warning', 'Informational'}:
            issues.append({'code': code, 'kind': 'unrecognised_severity', 'value': severity})
        if not values.get('message'):
            issues.append({'code': code, 'kind': 'missing_message'})
        entries.append({'event_code': code, 'severity': severity,
                        'pdf_pages': sorted({lines[start]['pdf_page']} |
                                            {x['pdf_page'] for v in fields.values() for x in v}),
                        'fields': {k: values.get(k) for k in CONTENT_FIELDS + ('vendor_category',)},
                        'source_lines': {k: [{a: b for a, b in x.items() if a != 'indent'} for x in v]
                                         for k, v in fields.items() if k in CONTENT_FIELDS + ('severity', 'vendor_category')}})
    raw = pdf_text('raw')
    # Alternate reading order: independently count labelled severity pairs.
    raw_code_severities = []
    raw_lines = raw.splitlines()
    current_code = None
    for i, line in enumerate(raw_lines):
        if CODE.fullmatch(line.strip()):
            current_code = line.strip()
        match = re.fullmatch(r'Severity\s+(Critical|Warning|Informational)', line.strip())
        if match:
            raw_code_severities.append((current_code, match[1]))
    actual_pairs = [(r['event_code'], r['severity']) for r in entries]
    raw_severities = Counter(severity for _, severity in raw_code_severities)
    duplicates = [k for k, n in Counter(r['event_code'] for r in entries).items() if n > 1]
    selected = [r for r in entries if r['severity'] in {'Critical', 'Warning'}]
    counts = Counter(r['severity'] for r in entries)
    summary = {
        'input_pdf': str(PDF), 'pdf_sha256': hashlib.sha256(PDF.read_bytes()).hexdigest(),
        'pdf_page_count': len(pages), 'content_input': 'PDF ONLY; no research events.json or prior concept classifier',
        'all_event_count': len(entries), 'severity_counts_layout': dict(counts),
        'severity_counts_raw': dict(raw_severities),
        'alternate_reading_order_pairs_identical': actual_pairs == raw_code_severities,
        'pair_differences': [list(p) for p in (set(actual_pairs) ^ set(raw_code_severities))][:50],
        'duplicate_codes': duplicates, 'selected_count': len(selected),
        'selected_prefix_count': len({re.match('[A-Z]+', r['event_code'])[0] for r in selected}),
        'issues': issues,
        'missing_content_fields_selected': {f: sum(not r['fields'].get(f) for r in selected) for f in CONTENT_FIELDS},
        'checks_scope': 'Extraction checks, not proof of concept or cause correctness; both text modes use Poppler.',
    }
    save_json(HERE/'selected_events.json', selected)
    save_json(HERE/'extraction_checks.json', summary)
    with (HERE/'selected_event_index.csv').open('w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['event_code', 'severity', 'pdf_pages', 'message', 'explanation', 'recommended_action', 'arguments', 'vendor_category'])
        for r in selected:
            writer.writerow([r['event_code'], r['severity'], ','.join(map(str, r['pdf_pages']))] + [r['fields'].get(x) or '' for x in CONTENT_FIELDS + ('vendor_category',)])
    print(json.dumps(summary, indent=2), flush=True)


def mine():
    import spacy
    nlp = spacy.load('en_core_web_sm', disable=['ner'])
    rows = json.loads((HERE/'selected_events.json').read_text())
    units = defaultdict(list)
    for row in rows:
        for field in CONTENT_FIELDS:
            text = row['fields'].get(field)
            if text:
                units[text].append((row['event_code'], field))
    terms = {}
    records = {r['event_code']: {'event_code': r['event_code'], 'terms': set(), 'sentence_candidates': []} for r in rows}
    clauses = []

    def add(span, kind, refs, sentence):
        tokens = list(span)
        while tokens and (tokens[0].pos_ in {'DET', 'PRON', 'SPACE', 'PUNCT'}):
            if tokens[0].lower_ in {'no', 'neither'}:
                break
            tokens.pop(0)
        while tokens and tokens[-1].is_punct:
            tokens.pop()
        if not tokens or len(tokens) > 8 or not any(t.pos_ in {'NOUN', 'PROPN'} for t in tokens):
            return
        if any(t.like_url or t.like_email for t in tokens):
            return
        phrase = normalized(' '.join(t.lemma_.lower() if t.pos_ == 'NOUN' else t.lower_ for t in tokens))
        if len(phrase) < 3 or not re.search('[a-z]', phrase) or re.search(r'\barg\d+\b|https?\b|www\b', phrase):
            return
        start, end = tokens[0].idx, tokens[-1].idx+len(tokens[-1])
        surface = span.doc.text[start:end]
        obj = terms.setdefault(phrase, {'events': set(), 'fields': defaultdict(set), 'forms': Counter(), 'kinds': set(), 'evidence': []})
        obj['forms'][surface] += len(refs)
        obj['kinds'].add(kind)
        for code, field in refs:
            obj['events'].add(code)
            obj['fields'][field].add(code)
            records[code]['terms'].add(phrase)
            if len(obj['evidence']) < 5 and not any(e['event_code'] == code and e['field'] == field for e in obj['evidence']):
                obj['evidence'].append({'event_code': code, 'field': field, 'surface': surface,
                                        'start': start, 'end': end, 'sentence': sentence})

    print('Mining', len(rows), 'selected PDF events;', len(units), 'distinct field texts', flush=True)
    for i, (doc, refs) in enumerate(nlp.pipe(units.items(), as_tuples=True, batch_size=48)):
        for chunk in doc.noun_chunks:
            add(chunk, 'noun_phrase', refs, chunk.sent.text)
        for token in doc:
            if token.pos_ in {'NOUN', 'PROPN'} and not token.is_stop and len(token.text) > 2:
                add(doc[token.i:token.i+1], 'noun', refs, token.sent.text)
                lefts = [t for t in token.lefts if t.dep_ in {'compound', 'amod'}]
                if lefts:
                    add(doc[min(t.left_edge.i for t in lefts):token.i+1], 'compound', refs, token.sent.text)
            if token.pos_ == 'VERB':
                for child in token.children:
                    if child.dep_ in {'dobj', 'obj'} and child.right_edge.i-token.i < 12:
                        add(doc[token.i:child.right_edge.i+1], 'verb_object_phrase', refs, token.sent.text)
        for sent in doc.sents:
            signals = []
            # Context cues, not semantic labels or validated cause assertions.
            if re.search(r'\b(due to|because|caused by|causes? of|results? from|may be caused|can be caused)\b', sent.text, re.I):
                signals.append('explicit_causal_language_candidate')
            if re.search(r'\b(if|unless|before|after|only when|until|do not|must not)\b', sent.text, re.I):
                signals.append('condition_sequence_or_prohibition_candidate')
            if signals:
                for code, field in refs:
                    index = len(clauses)
                    clauses.append({'event_code': code, 'field': field, 'start': sent.start_char,
                                    'end': sent.end_char, 'quote': sent.text, 'signals': signals})
                    records[code]['sentence_candidates'].append(index)
        if i and i % 1200 == 0:
            print('Processed field texts:', i, flush=True)
    by_code = {r['event_code']: r for r in rows}
    export = []
    for term, obj in terms.items():
        evidence = obj['evidence']
        for e in evidence:
            row = by_code[e['event_code']]
            assert row['fields'][e['field']][e['start']:e['end']] == e['surface']
            e['pdf_pages'] = sorted({x['pdf_page'] for x in row['source_lines'][e['field']]})
        export.append({'term': term, 'event_count': len(obj['events']), 'event_codes': sorted(obj['events']),
                       'field_event_counts': {k: len(v) for k, v in obj['fields'].items()},
                       'surface_forms': dict(obj['forms'].most_common(8)), 'extraction_kinds': sorted(obj['kinds']), 'evidence': evidence})
    export.sort(key=lambda x: (-x['event_count'], x['term']))
    for c in clauses:
        row = by_code[c['event_code']]
        assert row['fields'][c['field']][c['start']:c['end']] == c['quote']
        c['pdf_pages'] = sorted({x['pdf_page'] for x in row['source_lines'][c['field']]})
    for row in records.values():
        row['terms'] = sorted(row['terms'])
    save_json(HERE/'candidate_terms.json', export)
    save_json(HERE/'per_event_candidates.json', list(records.values()))
    save_json(HERE/'context_candidates.json', clauses)
    with (HERE/'candidate_terms.csv').open('w', newline='') as f:
        w = csv.writer(f)
        w.writerow(['term', 'event_count', 'message_events', 'explanation_events', 'action_events', 'example_code', 'example_pages', 'example_sentence'])
        for t in export:
            e = t['evidence'][0]
            w.writerow([t['term'], t['event_count']] + [t['field_event_counts'].get(k, 0) for k in CONTENT_FIELDS[:3]] +
                       [e['event_code'], ','.join(map(str, e['pdf_pages'])), e['sentence']])
    save_json(HERE/'mining_checks.json', {'processed_events': len(records), 'distinct_field_texts': len(units),
               'candidate_term_count': len(export), 'context_candidate_count': len(clauses),
               'events_without_candidate_terms': [k for k, v in records.items() if not v['terms']],
               'exact_span_checks': 'passed for every stored evidence span and context candidate',
               'model': 'spaCy en_core_web_sm', 'meaning': 'Linguistic candidates; no class assignments or cause assertions are inferred from frequency.'})
    print('Terms:', len(export), '; context candidates:', len(clauses), flush=True)


def cluster():
    import torch
    from sentence_transformers import SentenceTransformer
    from sklearn.cluster import AgglomerativeClustering
    torch.set_num_threads(3)
    terms = json.loads((HERE/'candidate_terms.json').read_text())
    # A support threshold is disclosed; singletons remain available in the complete term inventory.
    recurrent = [t for t in terms if t['event_count'] >= 4 and len(t['term'].split()) >= 2]
    recurrent = recurrent[:3000]
    model = SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2', local_files_only=True)
    vectors = model.encode([t['term'] for t in recurrent], normalize_embeddings=True, batch_size=96, show_progress_bar=False)
    labels = AgglomerativeClustering(n_clusters=None, metric='cosine', linkage='complete', distance_threshold=0.23).fit_predict(vectors)
    groups = defaultdict(list)
    for term, label in zip(recurrent, labels):
        groups[int(label)].append(term)
    result = []
    for values in groups.values():
        codes = sorted({c for t in values for c in t['event_codes']})
        result.append({'representative': values[0]['term'], 'term_count': len(values), 'event_count': len(codes),
                       'terms': [t['term'] for t in values], 'event_codes': codes,
                       'evidence': [t['evidence'][0] for t in values[:5]],
                       'status': 'UNREVIEWED_SIMILARITY_GROUP_NOT_A_CLASS_OR_SYNONYM_ASSERTION'})
    result.sort(key=lambda g: (-g['term_count'], -g['event_count'], g['representative']))
    for i, g in enumerate(result, 1):
        g['candidate_group_id'] = f'G{i:04d}'
    save_json(HERE/'similarity_groups.json', result)
    save_json(HERE/'clustering_checks.json', {'phrase_count': len(recurrent), 'minimum_event_support': 4,
        'phrase_cap': 3000, 'minimum_words': 2, 'model': 'all-MiniLM-L6-v2',
        'algorithm': 'complete-link agglomerative, cosine distance < 0.23',
        'all_group_count_including_singletons': len(result),
        'multi_phrase_group_count': sum(g['term_count'] > 1 for g in result),
        'seed_concept_labels': None,
        'limitation': 'Phrase similarity is not synonymy, subsumption, causal evidence or expert validation.'})
    print('Similarity groups:', len(result), '; multi-phrase:', sum(g['term_count'] > 1 for g in result), flush=True)


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('stage', choices=['extract', 'mine', 'cluster', 'all'])
    stage = p.parse_args().stage
    if stage in {'extract', 'all'}:
        extract()
    if stage in {'mine', 'all'}:
        mine()
    if stage in {'cluster', 'all'}:
        cluster()
