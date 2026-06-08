from datetime import datetime, timezone, timedelta
from fsrs import Scheduler, Card, Rating
import json
import math




# =================== MAIN REVIEW FUNCTION =======================
def schedulerReview(adapt_data: dict, grade: int):
    def _getR(card):
        return fsrs.get_card_retrievability(card)

    fsrs = Scheduler()
    scheduling = adapt_data["scheduling"]

    tempCardDict = {
        "card_id":     adapt_data.get("id"),
        "stability":   scheduling.get("S"),
        "difficulty":  scheduling.get("D"),
        "last_review": scheduling.get("lastReview"),
        "due":         adapt_data.get("due"),
        "state":       scheduling.get("state", 2),
        "step":        scheduling.get("step", 0),
    }

    # To object
    tempCard = Card.from_json(json.dumps(tempCardDict))

    # Reviews
    tempCard, _ = fsrs.review_card(tempCard, grade)
    due = tempCard.due.isoformat() # to be returned

    # To dict
    tempCardDict = tempCard.to_dict()

    schedulingDict = {
        "S": tempCardDict["stability"],
        "D": tempCardDict["difficulty"],
        "R": _getR(tempCard),
        "tauG": adapt_data["scheduling"]["tauG"],
        "state": tempCardDict["state"],
        "step": tempCardDict["step"],
        "lastReview": tempCardDict["last_review"],
        "exertion": adapt_data["scheduling"]["exertion"]
    }

    return schedulingDict, due