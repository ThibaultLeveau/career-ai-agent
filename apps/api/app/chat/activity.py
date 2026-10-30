"""Public progress derived from the research tasks that are actually running."""

from dataclasses import dataclass, field

LABELS = {
    "analyzer": "Query Analyzer Agent",
    "database": "Database Agents",
    "database-combined": "Database Agents",
    "database-separate": "Database Agents",
    "rag-broad": "RAG Agents",
    "rag-scoped": "RAG Agents",
    "answer": "Answer Agent",
}


@dataclass
class Task:
    lane: str
    criteria: dict[str, str]
    state: str = "running"
    empty: bool = False


def criterion_label(requirement: str) -> str:
    text = " ".join(requirement.split())
    # Bound labels in the browser's UTF-16 units, including non-BMP characters.
    encoded = text.encode("utf-16-le", errors="replace")
    if len(encoded) <= 80:
        return text
    return encoded[:78].decode("utf-16-le", errors="ignore").rstrip() + "…"


@dataclass
class Activity:
    tasks: dict[str, Task] = field(default_factory=dict)
    phase: dict | None = None

    def set_phase(self, stage: str, message: str) -> dict:
        self.tasks.clear()
        lane = {
            "analyzing": "analyzer",
            "answering": "answer",
            "database": "database",
        }[stage]
        self.phase = {
            "id": lane,
            "agent": LABELS[lane],
            "message": message,
            "state": "running",
        }
        return self.payload(stage, lane)

    def start(self, key: str, lane: str, criteria: dict[str, str]) -> dict:
        self.phase = None
        self.tasks[key] = Task(
            lane, {key: criterion_label(value) for key, value in criteria.items()}
        )
        return self.payload("database" if lane.startswith("database") else "rag", lane)

    def finish(self, key: str, *, failed: bool, empty: bool = False) -> dict | None:
        task = self.tasks.get(key)
        if task is None or task.state != "running":
            return None
        task.state = "error" if failed else "complete"
        task.empty = empty
        return self.payload(
            "database" if task.lane.startswith("database") else "rag", task.lane
        )

    def payload(self, stage: str, changed: str) -> dict:
        activities = []
        if self.phase:
            activities.append(dict(self.phase))
        for lane in LABELS:
            tasks = [task for task in self.tasks.values() if task.lane == lane]
            if not tasks:
                continue
            active = [task for task in tasks if task.state == "running"]
            running = bool(active)
            failed = any(task.state == "error" for task in tasks)
            criteria = {
                key: label for task in active for key, label in task.criteria.items()
            }
            count = len(criteria)
            criteria_label = f"{count} {'criterion' if count == 1 else 'criteria'}"
            if lane.startswith("database"):
                if count:
                    suffix = (
                        " independently"
                        if lane == "database-separate"
                        else " together"
                        if lane == "database-combined"
                        else " against career records"
                    )
                    message = f"Checking {criteria_label}{suffix}"
                    if lane == "database-combined" and len(active) > 1:
                        message = f"Checking combinations of {criteria_label}"
                    names = ", ".join(criteria[key] for key in sorted(criteria))
                    message += f" ({names})…"
                else:
                    message = "Searching relevant career records…"
                complete = "Career record checks complete."
                if all(task.empty for task in tasks):
                    complete = "No matching records for these criteria."
            else:
                count = len(active)
                searches = f"{count} {'search' if count == 1 else 'searches'}"
                message = (
                    f"Running {searches} across career text…"
                    if lane == "rag-broad"
                    else f"Running {searches} within matching records…"
                )
                complete = "Supporting text research complete."
            if not running:
                message = (
                    "Some searches were unavailable; keeping verified evidence."
                    if failed
                    else complete
                )
            activities.append(
                {
                    "id": lane,
                    "agent": LABELS[lane],
                    "message": message,
                    "state": "running"
                    if running
                    else "error"
                    if failed
                    else "complete",
                }
            )
        current = next(item for item in activities if item["id"] == changed)
        return {
            "stage": stage,
            "message": f"{current['agent']} — {current['message']}",
            "activities": activities,
        }
