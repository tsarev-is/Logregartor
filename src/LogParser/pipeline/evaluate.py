"""Оценка группировки шаблонов отдельно от классификации аномалий."""

import csv
from collections import Counter

from .artifacts import read_events, read_report


def grouping_metrics(expected, predicted):
    if len(expected) != len(predicted) or not expected:
        raise ValueError("grouping evaluation requires equally sized, nonempty label lists")
    true_counts, predicted_counts = Counter(expected), Counter(predicted)
    joint = Counter(zip(expected, predicted))
    pairs = lambda n: n * (n - 1) // 2
    true_pairs = sum(pairs(n) for n in true_counts.values())
    predicted_pairs = sum(pairs(n) for n in predicted_counts.values())
    correct_pairs = sum(pairs(n) for n in joint.values())
    precision = correct_pairs / predicted_pairs if predicted_pairs else float(true_pairs == 0)
    recall = correct_pairs / true_pairs if true_pairs else 1.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    exact = sum(n for (truth, prediction), n in joint.items()
                if n == true_counts[truth] == predicted_counts[prediction])
    return {"rows": len(expected), "reference_groups": len(true_counts), "predicted_groups": len(predicted_counts),
            "pairwise_precision": precision, "pairwise_recall": recall, "pairwise_f1": f1,
            "grouping_accuracy": exact / len(expected)}


def evaluate(events, report_path, reference_csv):
    report = read_report(events, report_path)
    if len(report["files"]) != 1:
        raise ValueError("evaluate requires the single OpenStack 2k source")
    expected, predicted = [], []
    statuses = Counter()
    with open(reference_csv, encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream)
        for event in read_events(events, report):
            row = next(reader, None)
            if row is None or int(row["LineId"]) != event["line_start"]:
                raise ValueError("CSV and events are not aligned by physical line")
            if event["template_status"] == "pending":
                raise ValueError("evaluate requires transformed events")
            for key, field in (("source_name", "Logrecord"), ("level", "Level"), ("component", "Component"), ("message", "Content")):
                if event[key] != row[field]:
                    raise ValueError(f"parsed field differs from reference at line {row['LineId']}: {key}")
            if event["timestamp_raw"] != row["Date"] + " " + row["Time"] or event["pid"] != int(row["Pid"]):
                raise ValueError("parsed timestamp/PID differs from reference")
            if event["context_raw"] != "[" + row["ADDR"] + "]":
                raise ValueError("parsed context differs from reference")
            expected.append(row["EventId"])
            # Unmatched messages must not become one artificial shared cluster.
            predicted.append(event["template_id"] or "unmatched:" + event["event_id"])
            statuses[event["template_status"]] += 1
        if next(reader, None) is not None:
            raise ValueError("CSV contains more rows than events")
    return {**grouping_metrics(expected, predicted), "template_statuses": dict(statuses),
            "template_version": report.get("template_version"),
            "note": "Template grouping evaluation only; this is not anomaly detection accuracy."}
