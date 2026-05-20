import math


class AdaptivePerformanceModel:
    """
    FSRS-6 Fitness-Fatigue Model (realistic version)
    """

    def __init__(self):
        # ==================== FIXED PARAMETERS ====================
        self.baseline = 1800.0      # 30 min untrained
        self.target   = 1200.0      # 20 min goal
        self.m        = 0.35
        self.tau_G    = 7.0
        self.kp       = 0.05

        # ==================== STATE ====================
        self.peak_fitness = 180.0          # start more conservatively
        self.fatigue      = 60.0
        self.current_day  = 0
        self.last_workout_day = 0
        self.stability    = 25.0           # more realistic starting stability
        self.difficulty   = 5.0

    # ====================== HELPER TABLES ======================
    def _f_g(self, g):
        """Much smaller fitness gain per extra day of stability"""
        return {0: 2.0, 1: 4.0, 2: 8.0, 3: 12.0}[g]

    def _h_g(self, g):
        """Fatigue cost per grade"""
        return {0: 180.0, 1: 130.0, 2: 90.0, 3: 50.0}[g]

    # ====================== FSRS-6 R (manual) ======================
    def _get_r(self, days_since):
        if days_since <= 0:
            return 1.0
        S = self.stability
        d = -0.3
        f = (0.9 ** (1 / d)) - 1
        return (1 + f * days_since / S) ** d

    # ====================== DAILY DECAY ======================
    def daily_decay(self):
        self.current_day += 1
        self.fatigue *= math.exp(-1.0 / self.tau_G)

    # ====================== WORKOUT ======================
    def workout(self, grade, exertion=1.0):
        self.current_day += 1

        # Realistic stability gain
        stability_gain = {0: 1.5, 1: 4.0, 2: 8.0, 3: 13.0}[grade]
        self.stability += stability_gain

        # Fitness gain
        delta_peak = self._f_g(grade) * stability_gain
        self.peak_fitness = max(self.peak_fitness, self.peak_fitness + delta_peak)

        # Fatigue gain
        delta_fatigue = self._h_g(grade) * exertion
        self.fatigue += delta_fatigue

        self.last_workout_day = self.current_day

    # ====================== GETTERS ======================
    def get_r(self):
        days_since = self.current_day - self.last_workout_day
        return self._get_r(days_since)

    def get_fitness_cu(self):
        return self.peak_fitness * self.get_r()

    def get_net_cu(self):
        return self.get_fitness_cu() - self.m * self.fatigue

    def get_predicted_time(self):
        return self.baseline - self.get_net_cu()

    def get_r_final(self):
        predicted = self.get_predicted_time()
        return 1 / (1 + math.exp(-self.kp * (self.target - predicted)))

    # ====================== SIMULATE ======================
    def simulate_days(self, days, training_days):
        for d in range(1, days + 1):
            if d in training_days:
                self.workout(grade=2, exertion=1.0)   # Good workout
            else:
                self.daily_decay()
            print(f"Day {d:3d} | Pred: {self.get_predicted_time():6.1f}s | "
                  f"R_final: {self.get_r_final():.3f}")


# ====================== RUN ======================
if __name__ == "__main__":
    model = AdaptivePerformanceModel()
    print("Initial predicted time:", model.get_predicted_time())
    print("Initial R_final:", model.get_r_final())
    print("-" * 60)
    model.simulate_days(60, training_days=list(range(1, 31)))