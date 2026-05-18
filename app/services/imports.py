"""Parsing des fichiers d'import d'exercices (CSV, TSV, format Anki).

Utilisé par la route ``/parents/import`` pour pré-traiter le contenu uploadé
avant insertion en base. Pas de contexte Flask requis : prend une chaîne et
retourne des dicts ``{prompt, answer, category}``.
"""

import csv
from io import StringIO
from typing import Dict, List


def _parse_import_rows(
    file_content: str, import_format: str, delimiter: str
) -> List[Dict[str, str]]:
    rows: List[Dict[str, str]] = []
    if import_format == "anki":
        for raw_line in file_content.splitlines():
            line = raw_line.strip()
            if not line:
                continue
            if "\t" in line:
                parts = [part.strip() for part in line.split("\t", 2)]
            elif ";" in line:
                parts = [part.strip() for part in line.split(";", 2)]
            else:
                parts = [part.strip() for part in line.split(",", 2)]
            if len(parts) < 2:
                continue
            rows.append({"prompt": parts[0], "answer": parts[1], "category": "custom"})
        return rows

    safe_delimiter = (delimiter or ",")[0]
    csv_reader = csv.reader(StringIO(file_content), delimiter=safe_delimiter)
    headers: List[str] = []
    for index, row in enumerate(csv_reader):
        if not row:
            continue
        if index == 0 and any(cell.lower() in {"prompt", "question", "answer", "reponse"} for cell in row):
            headers = [cell.strip().lower() for cell in row]
            continue
        if headers:
            row_map = {headers[i]: row[i].strip() if i < len(row) else "" for i in range(len(headers))}
            prompt = row_map.get("prompt") or row_map.get("question") or ""
            answer = row_map.get("answer") or row_map.get("reponse") or ""
            category = row_map.get("category") or row_map.get("categorie") or "custom"
        else:
            prompt = row[0].strip() if len(row) > 0 else ""
            answer = row[1].strip() if len(row) > 1 else ""
            category = row[2].strip() if len(row) > 2 else "custom"
        if prompt and answer:
            rows.append({"prompt": prompt, "answer": answer, "category": category or "custom"})
    return rows
