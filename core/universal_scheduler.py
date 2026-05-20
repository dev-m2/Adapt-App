from datetime import datetime, timezone, timedelta
from fsrs import Scheduler, Card, Rating
import json
import math

# Calculate new decayed fatigue, new decayed fitness for a card

class UniversalScheduler:
    def __init__(self, params: dict):
        self.m    = params["m"] # fatigue weight
        self.kp   = params["kp"] # logistic steepness
        self.fsrs = Scheduler()

    # ================= HELPER FUNCTIONS ========================
    def _newPeakFitness(self, old_peak_fitness, old_s, new_s, grade):

        delta = [2.0, 4.0, 8.0, 12.0][grade]  * (new_s - old_s)
        return max(old_peak_fitness, old_peak_fitness + delta)


    def _newFatigue(self, old_fatigue, grade, exertion):
        delta = [180.0, 130.0, 90.0, 50.0][grade] * exertion
        return old_fatigue + delta
    
    def _getR(self, card):
        return self.fsrs.get_card_retrievability(card) 


    # =================== MAIN REVIEW FUNCTION =======================
    def SchedulerReview(self, adapt_data: dict, grade: int):    
        scheduling = adapt_data["scheduling"]

        # === SAFE CARD DICT — always include "due" as a valid string ===
        due_value = adapt_data.get("due")
        if isinstance(due_value, str) and due_value.strip():
            final_due = due_value
        else:
            # Fallback for new cards that have never been reviewed
            final_due = datetime.now(timezone.utc).isoformat(timespec='milliseconds')

        tempCardDict = {
            "card_id":     adapt_data.get("id"),
            "stability":   scheduling.get("S"),
            "difficulty":  scheduling.get("D"),
            "last_review": scheduling.get("lastReview"),
            "due":         final_due,                    # ← always a string
            "state":       scheduling.get("state", 2),
            "step":        scheduling.get("step", 0),
        }

        tempCard = Card.from_json(json.dumps(tempCardDict))

        # === rest of the method stays exactly the same ===
        if grade == 0:
            tempCard, _ = self.fsrs.review_card(tempCard, Rating.Again)
        elif grade == 1:
            tempCard, _ = self.fsrs.review_card(tempCard, Rating.Hard)
        elif grade == 2:
            tempCard, _ = self.fsrs.review_card(tempCard, Rating.Good)
        elif grade == 3:
            tempCard, _ = self.fsrs.review_card(tempCard, Rating.Easy)
        else:
            print("Faulty input!")
            return None, None

        tempCardDict = tempCard.to_dict()

        newPeakFitness = self._newPeakFitness(
            old_peak_fitness = adapt_data["state"]["peakFitness"],
            old_s            = adapt_data["scheduling"]["S"],
            new_s            = tempCardDict["stability"],
            grade            = grade
        )

        newFatigue = self._newFatigue(
            old_fatigue = adapt_data["state"]["fatigue"],
            grade       = grade,
            exertion    = adapt_data["scheduling"]["exertion"]
        )

        # To be returned
        newDue = tempCard.due.isoformat()

        schedulingDict = {
            "S": tempCardDict["stability"],
            "D": tempCardDict["difficulty"],
            "R": self._getR(tempCard),
            "tauG": adapt_data["scheduling"]["tauG"],
            "state": tempCardDict["state"],
            "step": tempCardDict["step"],
            "lastReview": tempCardDict["last_review"],
            "exertion": adapt_data["scheduling"]["exertion"]
        }

        stateDict = {
            "peakFitness": newPeakFitness,
            "peakFitnessDate": datetime.now(timezone.utc).isoformat(),
            "fitness": newPeakFitness,
            "fatigue": newFatigue
        }

        return schedulingDict, stateDict, newDue

    def fitnessFatigueDue(self, adapt_data: dict) -> datetime:
        if adapt_data["content"].get("type") != "run":
            raise ValueError("This method is only for 'run' adaptations")

        content = adapt_data["content"]
        state = adapt_data["state"]
        scheduling = adapt_data["scheduling"]

        # Load variables
        peak_fitness = state["peakFitness"]
        fatigue_0 = state["fatigue"]
        baseline = float(content["baseline"])
        target = float(content["target"])
        net_direction = content.get("netDirection", "negative")
        tau_g = scheduling.get("tauG", 7.0)
        kp = self.kp

        # Safe card reconstruction
        due_value = adapt_data.get("due")
        final_due = due_value if isinstance(due_value, str) and due_value.strip() else \
                    datetime.now(timezone.utc).isoformat(timespec='milliseconds')

        temp_card_dict = {
            "card_id":     adapt_data.get("id"),
            "stability":   scheduling.get("S"),
            "difficulty":  scheduling.get("D"),
            "last_review": scheduling.get("lastReview"),
            "due":         final_due,
            "state":       scheduling.get("state", 2),
            "step":        scheduling.get("step", 0),
        }

        temp_card = Card.from_json(json.dumps(temp_card_dict))

        sign = -1 if net_direction == "negative" else 1
        today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)

        crossings = 0
        previous_r = None

        for day in range(1, 730):
            t = day
            future_datetime = (temp_card_dict["last_review"] + timedelta(days=t)
                               if temp_card_dict["last_review"] else today + timedelta(days=t))

            # Fitness decays with FSRS retrievability
            r_fitness = self.fsrs.get_card_retrievability(temp_card, current_datetime=future_datetime)
            fitness_t = peak_fitness * r_fitness

            # Fatigue decays exponentially
            fatigue_t = fatigue_0 * math.exp(-t / tau_g)

            net = fitness_t - fatigue_t
            predicted_time = baseline + (sign * net)

            # Your R_final formula
            r_system = 1 / (1 + math.exp(-kp * (target - predicted_time)))

            # ←←← THIS IS THE CHANGE YOU WANTED
            threshold = 0.9

            if previous_r is not None:
                if previous_r >= threshold and r_system < threshold:
                    crossings += 1
                    if crossings == 2:
                        return today + timedelta(days=day)

            previous_r = r_system

        # Fallback
        return today + timedelta(days=30)


if __name__ == "__main__":
    scheduler = Scheduler()
    card = Card(
            stability=30.0,
            difficulty=5.0,
            last_review=state["lastReviewDate"]
        )

    print(getR())

