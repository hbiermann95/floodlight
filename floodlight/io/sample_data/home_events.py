import pandas as pd
from floodlight.core.events import Events


# 1st half
home_events_ht1 = pd.DataFrame()

home_events_ht1 = home_events_ht1.append(
    {
        "eID": "KickoffWhistle",
        "gameclock": 0 / 5,
        "outcome": None,
    },
    ignore_index=True,
)

home_events_ht1 = home_events_ht1.append(
    {
        "eID": "Kickoff",
        "gameclock": 0 / 5,
        "outcome": None,
    },
    ignore_index=True,
)

home_events_ht1 = home_events_ht1.append(
    {
        "eID": "Pass",
        "gameclock": 0 / 5,
        "outcome": 1,
    },
    ignore_index=True,
)

home_events_ht1 = home_events_ht1.append(
    {
        "eID": "Dribbling",
        "gameclock": 25 / 5,
        "outcome": 1,
    },
    ignore_index=True,
)

home_events_ht1 = home_events_ht1.append(
    {
        "eID": "Pass",
        "gameclock": 75 / 5,
        "outcome": 1,
    },
    ignore_index=True,
)

home_events_ht1 = home_events_ht1.append(
    {
        "eID": "Pass",
        "gameclock": 75 / 5,
        "outcome": 1,
    },
    ignore_index=True,
)

home_events_ht1 = home_events_ht1.append(
    {
        "eID": "Dribbling",
        "gameclock": 100 / 5,
        "outcome": 1,
    },
    ignore_index=True,
)

home_events_ht1 = home_events_ht1.append(
    {
        "eID": "Pass",
        "gameclock": 150 / 5,
        "outcome": 1,
    },
    ignore_index=True,
)

home_events_ht1 = home_events_ht1.append(
    {
        "eID": "Pass",
        "gameclock": 175 / 5,
        "outcome": 1,
    },
    ignore_index=True,
)

home_events_ht1 = home_events_ht1.append(
    {
        "eID": "Shot",
        "gameclock": 225 / 5,
        "outcome": 0,
    },
    ignore_index=True,
)


home_events_ht1 = home_events_ht1.append(
    {
        "eID": "Corner",
        "gameclock": 400 / 5,
        "outcome": 1,
    },
    ignore_index=True,
)

home_events_ht1 = home_events_ht1.append(
    {
        "eID": "Header",
        "gameclock": 425 / 5,
        "outcome": 1,
    },
    ignore_index=True,
)


home_events_ht1 = home_events_ht1.append(
    {
        "eID": "Goal",
        "gameclock": 450 / 5,
        "outcome": 1,
    },
    ignore_index=True,
)

home_events_ht1 = home_events_ht1.append(
    {
        "eID": "ThrowIn",
        "gameclock": 825 / 5,
        "outcome": 1,
    },
    ignore_index=True,
)

home_events_ht1 = home_events_ht1.append(
    {
        "eID": "Pass",
        "gameclock": 840 / 5,
        "outcome": 1,
    },
    ignore_index=True,
)

home_events_ht1 = home_events_ht1.append(
    {
        "eID": "Dribbling",
        "gameclock": 860 / 5,
        "outcome": 1,
    },
    ignore_index=True,
)

home_events_ht1 = home_events_ht1.append(
    {
        "eID": "FinalWhistle",
        "gameclock": 1010 / 5,
        "outcome": 875,
    },
    ignore_index=True,
)

home_events_ht1 = Events(home_events_ht1)


# 2nd half
home_events_ht2 = pd.DataFrame()

home_events_ht2 = home_events_ht2.append(
    {"eID": "KickoffWhistle", "gameclock": 0 / 5},
    ignore_index=True,
)

home_events_ht2 = home_events_ht2.append(
    {"eID": "Tackle", "gameclock": 125 / 5, "outcome": 0},
    ignore_index=True,
)


home_events_ht2 = home_events_ht2.append(
    {"eID": "Foul", "gameclock": 125 / 5, "outcome": None},
    ignore_index=True,
)

home_events_ht2 = home_events_ht2.append(
    {"eID": "Handball", "gameclock": 320 / 5, "outcome": None},
    ignore_index=True,
)

home_events_ht2 = home_events_ht2.append(
    {"eID": "Goalkick", "gameclock": 715 / 5, "outcome": None},
    ignore_index=True,
)

home_events_ht2 = home_events_ht2.append(
    {"eID": "FinalWhistle", "gameclock": 740 / 5, "outcome": None},
    ignore_index=True,
)

home_events_ht2 = Events(home_events_ht2)
