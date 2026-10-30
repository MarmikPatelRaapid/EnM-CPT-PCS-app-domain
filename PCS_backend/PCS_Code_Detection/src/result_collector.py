from src.tree.models import PCSCode


def classify(codes: list[PCSCode]) -> dict:
    billable: list[dict] = []
    non_billable: list[dict] = []

    for code in codes:
        entry = {
            "code": code.code,
            "procedure_name": code.procedure_name,
            "evidences": code.evidences,
        }
        if code.status == "billable":
            billable.append(entry)
        else:
            non_billable.append(entry)

    return {"billable": billable, "non_billable": non_billable}
