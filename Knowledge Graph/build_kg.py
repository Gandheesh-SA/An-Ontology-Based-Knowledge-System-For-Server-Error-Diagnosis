"""Build the Dell catalogue instance graph from the adjacent dataset and ontology."""
from collections import Counter
from pathlib import Path
import hashlib
import json
import re
from urllib.parse import quote

from rdflib import Graph, Literal, Namespace, RDF, RDFS, OWL, URIRef, XSD

OUT = Path(__file__).resolve().parent
ROOT = OUT.parent
D = Namespace("https://example.org/dell-troubleshooting#")
BASE = "https://example.org/dell-troubleshooting/data/"
COMPONENTS = {
    "GPU": "Processing", "Processor": "Processing", "Fan": "Cooling",
    "Battery": "Power", "Power supply": "Power", "DIMM": "Memory",
    "Memory": "Memory", "Storage drive": "Storage", "Storage controller": "Storage",
    "Network adapter": "Interconnect", "PCIe device": "Interconnect"
}
OPS = {"Check": "Diagnostic", "Collect": "Diagnostic", "Replace": "Corrective",
       "Reconnect": "Corrective", "Reseat": "Corrective", "Contact support": "Management"}


def build():
    dataset = json.loads((ROOT / "DATASET/events.json").read_text())
    schema = Graph().parse(ROOT / "ontology/ontology.ttl")
    g = Graph()
    g.bind("dell", D)
    g.bind("data", Namespace(BASE))
    counts = Counter()
    representatives = {}
    doc = dataset["source_document"]

    def value(node, prop, text, datatype=XSD.string):
        if text is not None and text != "":
            g.add((node, D[prop], Literal(text, datatype=datatype)))

    def typed(uri, cls):
        node = URIRef(uri)
        g.add((node, RDF.type, D[cls]))
        return node

    def concept(cls, name):
        node = typed(BASE + cls + "/" + quote(name, safe=""), cls)
        value(node, "name", name)
        value(node, "conceptId", cls + "/" + name)
        if cls == "ComponentType" and name in COMPONENTS:
            g.add((node, RDF.type, D[COMPONENTS[name] + "ComponentType"]))
        if cls == "OperationType" and name in OPS:
            g.add((node, RDF.type, D[OPS[name] + "OperationType"]))
        return node

    def link(node, prop, target):
        g.add((node, D[prop], target))

    def signed_link(node, prop, target, evidence, status):
        link(node, prop, target)
        key = hashlib.sha256(f"{node}|{prop}|{target}|{evidence}".encode()).hexdigest()
        ax = URIRef(BASE + "evidence/" + key)
        for p, o in [(RDF.type, OWL.Axiom), (OWL.annotatedSource, node),
                     (OWL.annotatedProperty, D[prop]), (OWL.annotatedTarget, target),
                     (D.evidenceQuote, Literal(evidence)), (D.mappingStatus, Literal(status)),
                     (D.evidenceDocumentId, Literal(doc["document_id"]))]:
            g.add((ax, p, o))
        for page in pages:
            g.add((ax, D.evidencePage, Literal(page, datatype=XSD.positiveInteger)))

    events = dataset["events"]
    assert len({e["event_code"] for e in events}) == len(events)
    for e in events:
        code = e["event_code"]
        uri = BASE + "event/" + quote(e["record_id"], safe="")
        event = typed(uri, "EventDefinition")
        pages = e["source_pages"]
        assert pages and all(1 <= p <= doc["pdf_page_count"] for p in pages)
        for page in pages:
            value(event, "sourcePage", page, XSD.positiveInteger)
        value(event, "sourceDocumentId", doc["document_id"])
        for field, prop in [("event_code","eventCode"), ("severity","severity"),
                            ("message","messageText"), ("explanation","explanationText"),
                            ("category","categoryText"), ("arguments","argumentText"),
                            ("recommended_action","recommendedResponseText"), ("source_text","sourceEventText")]:
            value(event, prop, e[field])
        for field in ["event_group", "notes", "additional_fields"]:
            if e[field]:
                value(event, "vendorMetadataText", json.dumps({field:e[field]}, ensure_ascii=False))
        k = e["knowledge"]
        cond = typed(uri + "/condition", "ReportedCondition")
        link(event, "describesCondition", cond)
        msg = k["reported_condition_text"]
        value(cond, "description", msg)
        if re.search(r"\bthreshold\b", msg, re.I):
            g.add((cond, RDF.type, D.ThresholdCondition))
        for field, prop, cls in [("component_type_candidates","concernsComponentType","ComponentType"),
                                 ("technical_property_candidates","concernsTechnicalProperty","TechnicalProperty")]:
            for c in k[field]:
                if c["source_phrase"].casefold() in msg.casefold():
                    signed_link(cond, prop, concept(cls,c["concept"]), msg, "automatic message phrase match")
        for n, cand in enumerate(k["possible_explanations"], 1):
            text = cand["text"]
            assert text in e[cand["source_field"]]
            if code == "BAT0009" or re.search(r"\b(?:due to|may be caused by|could be caused by|because of)\b",text,re.I):
                cause = typed(uri + f"/explanation/{n}", "PossibleExplanation")
                value(cause, "description", text)
                signed_link(cond,"hasPossibleExplanation",cause,text,"source causal wording; possible explanation")
            else:
                counts["causal candidates withheld"] += 1
        response = e["recommended_action"]
        if not response:
            continue
        proc = typed(uri + "/procedure", "RecoveryProcedure")
        link(event, "hasDocumentedResponse", proc)
        value(proc, "procedureText", response)
        # A star of exact matches avoids quadratic storage; OWL supplies closure.
        signature = " ".join(response.split())
        if signature in representatives:
            link(proc, "similarEvent", representatives[signature])
        else:
            representatives[signature] = proc
        items = [i for i in k["response_items"] if i["kind"] in {"numbered_instruction","sentence_candidate"}]
        if not items:
            items = [dict(order=1,text=response,kind="unsegmented response directive")]
            counts["whole response retained as single item"] += 1
        previous = None
        for item in items:
            order, text = item["order"], item["text"]
            assert text in response
            step = typed(uri + f"/instruction/{order}", "ProcedureInstruction")
            link(proc, "containsInstruction", step)
            value(step, "instructionText", text)
            value(step, "instructionOrder", order, XSD.positiveInteger)
            value(step, "sourceStepLabel", item.get("source_label"))
            g.add((step,D.mappingStatus,Literal(item["kind"])))
            if previous:
                link(previous, "appearsBefore", step)
            previous = step
            for c in item.get("operation_type_candidates", []):
                signed_link(step,"requestsOperationType",concept("OperationType",c["concept"]),text,"automatic operation candidate")
            for c in item.get("target_component_candidates", []):
                if re.search(r"\b(?:replace|reseat|reconnect|remove|inspect|install|check|verify)\s+(?:that\s+)?(?:the\s+)?(?:faulty\s+)?"+re.escape(c["source_phrase"])+r"\b",text,re.I):
                    signed_link(step,"targetsComponentType",concept("ComponentType",c["concept"]),text,"action and component phrase")
            for c in item.get("artifact_type_candidates", []):
                for verbs, prop in [("check|inspect|review|read","usesArtifactType"),
                                    ("collect|generate|create|export","requestsArtifactType")]:
                    if re.search(r"\b(?:"+verbs+r")\s+(?:(?:the|a|an|new|two)\s+){0,2}"+re.escape(c["source_phrase"]),text,re.I):
                        signed_link(step,prop,concept("TechnicalArtifactType",c["concept"]),text,"action and artifact phrase")
            if code == "BAT0009" and order in (2,3):
                phrase, prop = ("disconnect","attemptsToCorrectExplanation") if order == 2 else ("thermal exceptions","investigatesExplanation")
                assert phrase in e["explanation"] and ("reconnect" if order == 2 else "thermal") in text
                specific = typed(uri + f"/possibility/{order}", "PossibleExplanation")
                value(specific,"description",phrase)
                signed_link(cond,"hasPossibleExplanation",specific,e["explanation"],"source alternative")
                signed_link(step,prop,specific,text,"matched instruction to documented alternative")
        if code == "CTL45":
            evidence = "The DIMM is a part of the controller battery pack."
            assert evidence in response
            signed_link(concept("ComponentType","Controller battery pack"),"hasDocumentedPartType",concept("ComponentType","DIMM"),evidence,"explicit part statement")
    for prop in schema.subjects(RDF.type,OWL.ObjectProperty):
        counts[str(prop).split("#")[-1]] = len(list(g.triples((None,prop,None))))
    for e in events:
        n = URIRef(BASE+"event/"+quote(e["record_id"],safe=""))
        assert str(g.value(n,D.eventCode)) == e["event_code"]
        p = g.value(n,D.hasDocumentedResponse,any=False)
        if e["recommended_action"]:
            assert str(g.value(p,D.procedureText)) == e["recommended_action"]
            assert list(g.objects(p,D.containsInstruction))
    for path, fmt in [("knowledge_graph.ttl","turtle"),("knowledge_graph.owl","xml")]:
        g.serialize(OUT/path,format=fmt)
        loaded = Graph().parse(OUT/path,format=fmt)
        assert len(loaded)==len(g) and all(t in loaded for t in g)
        del loaded
    print(f"{len(events)} events; {len(g)} instance and evidence triples")
    print(json.dumps(counts,indent=2))


if __name__ == "__main__":
    build()
