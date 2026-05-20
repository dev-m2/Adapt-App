import math

params = {
    "tauF": 42.0, # fitness time constant;
    "tauG": 7.0, # fatigue time constant;
    "P0": 1800.0, # untrained baseline in seconds;
    "k": 8.0, # how much each unit of net-fitness, affects expected time P in seconds;
    "m": 0.35, # scales how much fatigue affects net; in net = F - m * G;
    "a": 0.8, # how much drive gives delta f
    "b": 2.2, # how much drive gives delta g
    "gamma": 80.0, # how much fatigue dempens how much delta f is gained with drive;
    "alpha": 0.25, # how much maesured trial performance updates expected performance
    "lambda_": 0.9, # how much of the 'blame' fatigue takes when correcting
    "gMax": 120.0, # maximum change in fatigue post-trial; we don't want it to jump too much;
    "gammaP": 0.05, #kp for the sigmoid probability?
}

def initState():
    state = {
        "F": 80.0, # fitness
        "G": 40.0, # fatigue
        "P": 0.0, # expected performance;s to-be calculated next;
        "day": 0,
        "history": [] # to-be list of dictionaries;
    }

    net = state["F"] - (params["m"] * state["G"])
    state["P"] = params["P0"] - (params["k"] * net)
    return state


