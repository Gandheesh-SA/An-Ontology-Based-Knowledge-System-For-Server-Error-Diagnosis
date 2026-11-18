"""Build the Dell Critical and Warning catalogue schema. Run with Python and RDFLib."""
from pathlib import Path
import re

from rdflib import BNode, Graph, Literal, Namespace, OWL, RDF, RDFS, URIRef, XSD
from rdflib.collection import Collection
from rdflib.compare import isomorphic

BASE = "https://example.org/dell-troubleshooting"
D = Namespace(BASE + "#")
NORIA = Namespace("https://w3id.org/noria/ontology/")
SAREF = Namespace("https://saref.etsi.org/core/")
DUL = Namespace("http://www.ontologydesignpatterns.org/ont/dul/DUL.owl#")

CLASSES = {
    'EventDefinition': 'A versioned Dell catalogue entry, not an observed incident.',
    'ComponentType': 'A reusable concept describing a component type, not an installed device.',
    'ReportedCondition': 'A source-supported reported state or problem pattern, scoped to its definition.',
    'TechnicalProperty': 'A property concept such as fan speed or voltage, not a measured value.',
    'PossibleExplanation': 'A documented possible explanation, retaining alternatives and uncertainty.',
    'RecoveryProcedure': 'A complete documented troubleshooting response, not a proven repair or executable workflow.',
    'ProcedureInstruction': 'A procedure-owned instruction occurrence, preserving its source context.',
    'OperationType': 'A reusable operation concept; classification does not establish safety or success.',
    'TechnicalArtifactType': 'A reusable type of information artifact, not an actual log file or generated report.',
}
PARENTS = {
    'HardwareComponentType': 'ComponentType',
    'FirmwareComponentType': 'ComponentType',
    **{n + 'ComponentType': 'HardwareComponentType' for n in
       ['Processing', 'Memory', 'Cooling', 'Storage', 'Power', 'Interconnect', 'Security']},
    **{n + 'Condition': 'ReportedCondition' for n in
       ['Availability', 'Threshold', 'Compatibility', 'Integrity', 'Error']},
    **{n + 'OperationType': 'OperationType' for n in ['Diagnostic', 'Corrective', 'Management']},
}
DATA = {
    'conceptId': (list(CLASSES), XSD.string, 'A stable identifier within this model.'),
    'name': (list(CLASSES), XSD.string, 'A readable source-grounded name.'),
    'sourceDocumentId': (list(CLASSES), XSD.string, 'Source guide and edition identifier; reusable concepts may have several sources.'),
    'sourcePage': (list(CLASSES), XSD.positiveInteger, 'Physical PDF page number; multiple pages may support an entity.'),
    'sourceQuote': (list(CLASSES), XSD.string, 'Supporting source wording; preserves qualifications.'),
    'eventCode': (['EventDefinition'], XSD.string, 'Original event code.'),
    'severity': (['EventDefinition'], XSD.string, 'Original Critical or Warning value in this dataset profile.'),
    'categoryText': (['EventDefinition'], XSD.string, 'Original Dell category and subsystem text.'),
    'messageText': (['EventDefinition'], XSD.string, 'Original message, retaining placeholders.'),
    'argumentText': (['EventDefinition'], XSD.string, 'Original documented placeholder names and meanings; not runtime bindings.'),
    'explanationText': (['EventDefinition'], XSD.string, 'Full original detailed-description section, including no-description statements.'),
    'recommendedResponseText': (['EventDefinition'], XSD.string, 'Full original response, including pure no-action policies and cautions.'),
    'sourceEventText': (['EventDefinition'], XSD.string, 'Complete extracted entry, preserving vendor metadata and repeated platform sections.'),
    'platformAlertText': (['EventDefinition'], XSD.string, 'Original platform-qualified applicability/default settings; not proof an alert was sent.'),
    'vendorMetadataText': (['EventDefinition'], XSD.string, 'Original label/value text for optional vendor fields, including LCD and trap identifiers.'),
    'description': (['ComponentType', 'ReportedCondition', 'TechnicalProperty', 'PossibleExplanation', 'OperationType', 'TechnicalArtifactType'], XSD.string, 'Meaning of this concept or source-scoped statement.'),
    'thresholdDirection': (['ThresholdCondition'], XSD.string, 'Source-supported ABOVE or BELOW relation to the threshold.'),
    'comparisonOperator': (['ThresholdCondition'], XSD.string, 'Optional source-supported LT, LE, GT, GE, EQ or NE comparison; preserves strict versus inclusive bounds.'),
    'thresholdLevel': (['ThresholdCondition'], XSD.string, 'Source-supported threshold band, such as Warning or Critical.'),
    'thresholdValue': (['ThresholdCondition'], XSD.decimal, 'A numeric threshold explicitly present in the source, not an observed measurement.'),
    'thresholdUnitText': (['ThresholdCondition'], XSD.string, 'Source unit for an explicit numeric threshold; no unit conversion implied.'),
    'qualifierText': (['ReportedCondition', 'PossibleExplanation'], XSD.string, 'Source wording such as may, either/or, or platform qualifications.'),
    'procedureText': (['RecoveryProcedure'], XSD.string, 'Complete response represented by this procedure, retaining order, conditions and cautions.'),
    'instructionText': (['ProcedureInstruction'], XSD.string, 'A reviewed instruction span with its local qualifications intact.'),
    'instructionOrder': (['ProcedureInstruction'], XSD.positiveInteger, 'Unique source reading position within the procedure, not an execution dependency.'),
    'instructionPath': (['ProcedureInstruction'], XSD.string, 'Optional source nesting position, such as 2.b; not a second ordering algorithm.'),
    'sourceStepLabel': (['ProcedureInstruction'], XSD.string, 'Original numbering or bullet label, where present.'),
    'conditionText': (['ProcedureInstruction'], XSD.string, 'An explicit conditional qualification, such as If installed; does not assert it holds.'),
    'restrictionText': (['ProcedureInstruction'], XSD.string, 'An explicit caution or prohibition; not a verified runtime guard.'),
    'toolText': (['ProcedureInstruction'], XSD.string, 'Documented tool, interface or command wording.'),
    'locationText': (['ProcedureInstruction'], XSD.string, 'Documented slot, bay or other location wording, preserving placeholders.'),
}
AXIOM_ANNOTATIONS = {
    'evidenceDocumentId': 'Guide and edition supporting this particular relationship.',
    'evidencePage': 'Physical PDF page supporting this particular relationship.',
    'evidenceQuote': 'Source wording supporting this particular relationship.',
    'mappingStatus': 'SOURCE_SUPPORTED_INTERPRETATION identifies a reviewed mapping, not vendor verification or repair success.',
    'relationshipCategory': 'UML presentation category; not a built-in OWL property characteristic.',
}
CQ = [
    'Which definition reports a given condition, component type and technical property?',
    'What documented possibilities explain this condition, retaining uncertainty and alternatives?',
    'What complete response is recommended, including no-action policies, conditions and warnings?',
    'Which instructions belong to a procedure, and in what source order and nesting?',
    'Which instruction investigates or attempts to address which documented possibility, with what source support?',
    'What information artifacts are used versus requested as outputs?',
    'Which explicit threshold direction, level, value and unit does the source document?',
    'Which source entry and pages support the retrieved recommendation and each interpreted relationship?',
]
# Local names follow the Dell UML. Characteristics are OWL axioms.
A = OWL.AsymmetricProperty
RELATIONS = [
    ("describesCondition", "EventDefinition", "ReportedCondition", [A], "Identifies a condition described by the event message."),
    ("concernsComponentType", "ReportedCondition", "ComponentType", [A], "Identifies the component kind affected by the condition."),
    ("concernsTechnicalProperty", "ReportedCondition", "TechnicalProperty", [A], "Identifies the property involved, such as fan speed."),
    ("hasPossibleExplanation", "ReportedCondition", "PossibleExplanation", [A], "Links a condition to a possibility supported by the source wording."),
    ("hasDocumentedResponse", "EventDefinition", "RecoveryProcedure", [A, OWL.FunctionalProperty], "Links an entry to its complete response block, which can contain alternatives."),
    ("containsInstruction", "RecoveryProcedure", "ProcedureInstruction", [A, OWL.InverseFunctionalProperty], "Owns an instruction occurrence within this response. Identical words in another response are a separate occurrence."),
    ("appearsBefore", "ProcedureInstruction", "ProcedureInstruction", [OWL.TransitiveProperty], "Earlier in the source order within one procedure. Population must check procedure boundaries and cycles."),
    ("requestsOperationType", "ProcedureInstruction", "OperationType", [A], "Classifies the work requested by the instruction."),
    ("targetsComponentType", "ProcedureInstruction", "ComponentType", [A], "Identifies the kind of component to check or act on."),
    ("usesArtifactType", "ProcedureInstruction", "TechnicalArtifactType", [A], "Identifies the kind of file or information inspected or used."),
    ("requestsArtifactType", "ProcedureInstruction", "TechnicalArtifactType", [A], "Identifies a deliverable requested for generation or collection."),
    ("investigatesExplanation", "ProcedureInstruction", "PossibleExplanation", [A], "Identifies a documented possibility that this instruction checks."),
    ("attemptsToCorrectExplanation", "ProcedureInstruction", "PossibleExplanation", [A], "Identifies a documented possibility this instruction seeks to remedy."),
    ("hasDocumentedPartType", "ComponentType", "ComponentType", [OWL.IrreflexiveProperty], "Records an explicitly documented whole-to-part link between distinct component kinds."),
    ("similarEvent", None, None, [OWL.ReflexiveProperty, OWL.SymmetricProperty, OWL.TransitiveProperty], "Same typed catalogue content signature, preserving order, qualifiers and values. Compare distinct records only from complete signatures after whitespace normalization. Reflexivity also relates every individual to itself."),
]

UPPER = {
    "InformationObject": ["EventDefinition", "ProcedureInstruction"],
    "Description": ["ReportedCondition", "PossibleExplanation"],
    "Plan": ["RecoveryProcedure"],
    "Concept": ["ComponentType", "OperationType", "TechnicalArtifactType", "TechnicalProperty"],
}
SOURCES = [
    "https://www.w3.org/TR/owl2-syntax/",
    "https://cdn.aaai.org/Symposia/Spring/1997/SS-97-06/SS97-06-005.pdf",
    "https://doi.org/10.1007/978-3-031-60635-9_2",
    "https://w3id.org/noria/ontology/",
    "https://saref.etsi.org/core/v4.1.1/",
    "http://www.ontologydesignpatterns.org/ont/dul/DUL.owl",
    "https://dl.dell.com/content/manual64973867-poweredge-servers-error-and-event-messages-reference-guide.pdf",
]


def declare(graph, name, kind, definition):
    term = D[name]
    label = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", name)
    graph.add((term, RDF.type, kind))
    graph.add((term, RDFS.label, Literal(label, lang="en")))
    graph.add((term, RDFS.comment, Literal(definition, lang="en")))
    graph.add((term, RDFS.isDefinedBy, URIRef(BASE)))
    return term


def domain_expression(graph, names):
    if len(names) == 1:
        return D[names[0]]
    expression, members = BNode(), BNode()
    graph.add((expression, RDF.type, OWL.Class))
    graph.add((expression, OWL.unionOf, members))
    Collection(graph, members, [D[name] for name in names])
    return expression


def build():
    graph = Graph()
    ontology = URIRef(BASE)
    for prefix, namespace in [("dell", D), ("noria", NORIA), ("dul", DUL), ("saref", SAREF)]:
        graph.bind(prefix, namespace)
    graph.add((ontology, RDF.type, OWL.Ontology))
    graph.add((ontology, OWL.versionIRI, URIRef(BASE + "/dell-catalogue/1.0")))
    graph.add((ontology, RDFS.label, Literal("Dell server troubleshooting catalogue ontology", lang="en")))
    graph.add((ontology, RDFS.comment, Literal("Schema for documented Critical and Warning entries, their explanations and recommended responses. External class IRIs are reused selectively.", lang="en")))
    for source in SOURCES:
        graph.add((ontology, RDFS.seeAlso, URIRef(source)))
    for name, definition in AXIOM_ANNOTATIONS.items():
        declare(graph, name, OWL.AnnotationProperty, definition)
    declare(graph, "competencyQuestion", OWL.AnnotationProperty, "A question the populated catalogue should answer.")
    for question in CQ:
        graph.add((ontology, D.competencyQuestion, Literal(question, lang="en")))
    for name, definition in CLASSES.items():
        declare(graph, name, OWL.Class, definition)
    for name, parent in PARENTS.items():
        label = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", name)
        declare(graph, name, OWL.Class, f"{label} within the Dell troubleshooting catalogue.")
        graph.add((D[name], RDFS.subClassOf, D[parent]))
    alignments = [(local, DUL[parent]) for parent, names in UPPER.items() for local in names]
    alignments.extend([("ComponentType", SAREF.FeatureKind), ("TechnicalProperty", SAREF.Property),
                       ("RecoveryProcedure", NORIA.OperationPlan)])
    for local, external in alignments:
        graph.add((external, RDF.type, OWL.Class))
        graph.add((D[local], RDFS.subClassOf, external))
    graph.add((NORIA.AnomalyPattern, RDF.type, OWL.Class))
    bridge = declare(graph, "describesAnomalyPattern", OWL.ObjectProperty,
                     "Optional link when a reported condition describes a specifically identified NORIA anomaly pattern.")
    graph.add((bridge, RDFS.domain, D.ReportedCondition))
    graph.add((bridge, RDFS.range, NORIA.AnomalyPattern))
    graph.add((bridge, D.relationshipCategory, Literal("Association")))
    for name, domain, target, traits, definition in RELATIONS:
        term = declare(graph, name, OWL.ObjectProperty, definition)
        if domain:
            graph.add((term, RDFS.domain, D[domain]))
            graph.add((term, RDFS.range, D[target]))
        for trait in traits:
            graph.add((term, RDF.type, trait))
        category = {"containsInstruction": "Composition", "hasDocumentedPartType": "Shared aggregation"}.get(name, "Association")
        graph.add((term, D.relationshipCategory, Literal(category)))
    for name, (domains, datatype, definition) in DATA.items():
        term = declare(graph, name, OWL.DatatypeProperty, definition)
        graph.add((term, RDFS.domain, domain_expression(graph, domains)))
        graph.add((term, RDFS.range, datatype))
    # Existence in both directions plus inverse functionality gives each item exactly one owner.
    inverse = BNode()
    graph.add((inverse, OWL.inverseOf, D.containsInstruction))
    for owner, prop, part in [(D.RecoveryProcedure, D.containsInstruction, D.ProcedureInstruction),
                              (D.ProcedureInstruction, inverse, D.RecoveryProcedure)]:
        restriction = BNode()
        graph.add((owner, RDFS.subClassOf, restriction))
        graph.add((restriction, RDF.type, OWL.Restriction))
        graph.add((restriction, OWL.onProperty, prop))
        graph.add((restriction, OWL.someValuesFrom, part))
    return graph


if __name__ == "__main__":
    graph = build()
    folder = Path(__file__).resolve().parent
    for filename, encoding in [("ontology.ttl", "turtle"), ("ontology.owl", "xml")]:
        data = graph.serialize(format=encoding, encoding="utf-8")
        recovered = Graph().parse(data=data, format=encoding)
        if not isomorphic(graph, recovered):
            raise ValueError(f"RDF round-trip failed for {filename}")
        (folder / filename).write_bytes(data)
    print(f"Verified both serializations of {len(graph)} RDF triples.")
