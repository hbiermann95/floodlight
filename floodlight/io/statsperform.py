import os.path
import warnings
from typing import Dict, Tuple, Union
from pathlib import Path

import numpy as np
import pandas as pd
from lxml import etree

from floodlight.io.utils import download_from_url, get_and_convert
from floodlight.core.code import Code
from floodlight.core.events import Events
from floodlight.core.pitch import Pitch
from floodlight.core.teamsheet import Teamsheet
from floodlight.core.xy import XY
from floodlight.settings import DATA_DIR


# ----------------------------- StatsPerform Open Format -------------------------------


def _create_metadata_from_open_csv_df(
    csv_df: pd.DataFrame,
) -> Tuple[Dict[int, tuple], Pitch]:
    """Creates meta information from a pd.DataFrame that results from parsing the open
    StatsPerform event data csv file.

    Parameters
    ----------
    csv_df: pd.DataFrame
        Data Frame with the parsed event data csv file.

    Returns
    -------
    periods: Dict[int, int]
        Dictionary with start and endframes:
            ``periods[segment] = (startframe, endframe)``.
    pitch: Pitch
        Playing Pitch object.
    """

    # create pitch
    pi_len = csv_df["pitch_dimension_long_side"].values[0]
    pi_wid = csv_df["pitch_dimension_short_side"].values[0]
    pitch = Pitch.from_template(
        "statsperform_open",
        length=pi_len,
        width=pi_wid,
        sport="football",
    )

    # create periods for segments, coded as jumps in the frame sequence
    periods = {}
    frame_values = csv_df["frame_count"].unique()

    seg_idx = np.where(np.diff(frame_values, prepend=frame_values[0]) > 1)
    seg_idx = np.insert(seg_idx, 0, 0)
    seg_idx = np.append(seg_idx, len(frame_values))
    for segment in range(len(seg_idx) - 1):
        start = int(frame_values[seg_idx[segment]])
        end = int(frame_values[seg_idx[segment + 1] - 1])
        periods[segment] = (start, end)

    return periods, pitch


def _read_open_event_csv_single_line(
    line: str,
) -> Tuple[Dict, str, str]:
    """Extracts all relevant information from a single line of StatsPerform's Event csv
    file (i.e. one single event in the data).

    Parameters
    ----------
    line: str
        One full line from StatsPerform's Event csv file.

    Returns
    -------
    event: Dict
        Dictionary with relevant event information in the form:
        ``event[attribute] = value``.
    """
    event = {}
    attrib = line.split(sep=",")

    # description
    event["eID"] = attrib[5].replace(" ", "")

    # relative time
    event["gameclock"] = float(attrib[4])
    event["frameclock"] = float(attrib[2])

    # segment, player and team
    segment = attrib[3]
    team = attrib[9]
    event["tID"] = team
    event["pID"] = attrib[8]

    # outcome
    event["outcome"] = np.nan
    if "Won" in attrib[5].split(" "):
        event["outcome"] = 1
    elif "Lost" in attrib[5].split(" "):
        event["outcome"] = 0

    # minute and second of game
    event["minute"] = np.floor(event["gameclock"] / 60)
    event["second"] = np.floor(event["gameclock"] - event["minute"] * 60)

    # additional information (qualifier)
    event["qualifier"] = {
        "event_id": attrib[1],
        "event_type_id": attrib[6],
        "sequencenumber": attrib[7],
        "jersey_no": attrib[10],
        "is_pass": attrib[11],
        "is_cross": attrib[12],
        "is_corner": attrib[13],
        "is_free_kick": attrib[14],
        "is_goal_kick": attrib[15],
        "passtypeid": attrib[16],
        "wintypeid": attrib[17],
        "savetypeid": attrib[18],
        "possessionnumber": attrib[19],
    }

    return event, team, segment


def read_teamsheets_from_open_data_csv(
    filepath_csv: Union[str, Path]
) -> Dict[str, Teamsheet]:
    """Parses the entire open StatsPerform tracking data csv file for unique jIDs
    (jerseynumbers) and creates teamsheets for both teams.

    Parameters
    ----------
    filepath_csv: str or pathlib.Path
        csv file where the position data in StatsPerform format is saved.

    Returns
    -------
    teamsheets: Dict[str, Teamsheet]
        Dictionary with teamsheets for the home team and the away team.
    """
    # read dat-file into pd.DataFrame
    csv_df = pd.read_csv(str(filepath_csv))

    # initialize team and ball ids
    team_ids = {"Home": 1.0, "Away": 2.0}
    ball_id = 4

    # check for additional tIDs
    for tID in csv_df["team_id"].unique():
        if not (tID in team_ids.values() or tID == ball_id or np.isnan(tID)):
            warnings.warn(f"tID {tID} did not match any of the standard tIDs "
                          f"({team_ids.values}) or the ball ID ({ball_id})!")

    # initialize teamsheets
    teamsheets = {
        "Home": pd.DataFrame(columns=["player", "jID", "pID", "tID"]),
        "Away": pd.DataFrame(columns=["player", "jID", "pID", "tID"]),
    }

    # parse player information
    for team in team_ids:
        team_id = team_ids[team]
        teamsheets[team]["player"] = [
            pID for pID in csv_df[csv_df["team_id"] == team_id]["player_id"].unique()
        ]
        teamsheets[team]["jID"] = [
            jID for jID in csv_df[csv_df["team_id"] == team_id]["jersey_no"].unique()
        ]
        teamsheets[team]["pID"] = [
            pID for pID in csv_df[csv_df["team_id"] == team_id]["player_id"].unique()
        ]
        teamsheets[team]["tID"] = team_id

    # create teamsheet objects
    for team in teamsheets:
        teamsheets[team] = Teamsheet(teamsheets[team])

    return teamsheets


def read_open_event_data_csv(
    filepath_events: Union[str, Path],
    home_teamsheet: Teamsheet = None,
    away_teamsheet: Teamsheet = None,
) -> Tuple[Events, Events, Events, Events, Teamsheet, Teamsheet]:
    """Parses an open StatsPerform Match Event csv file and extracts the event data and
    teamsheets.

    This function provides a high-level access to the particular openly published
    StatsPerform match events csv file (e.g. for the Pro Forum '22) and returns Event
    objects for both teams.

    Parameters
    ----------
    filepath_events: str or pathlib.Path
        Full path to xml File where the Event data in StatsPerform csv format is
        saved
    home_teamsheet: Teamsheet, optional
        Teamsheet-object for the home team used to create link dictionaries of the form
        `links[team][jID] = xID` and  `links[team][pID] = jID`. The links are used to
        map players to a specific xID in the respective XY objects. Should be supplied
        if that order matters. If given as None (default), teamsheet is extracted from
        the Match Information XML file.
    away_teamsheet: Teamsheet, optional
        Teamsheet-object for the away team. If given as None (default), teamsheet is
        extracted from the Match Information XML file.

    Returns
    -------
    data_objects: Tuple[Events, Events, Events, Events, Teamsheet, Teamsheet]
        Events-objects for both teams and both halves.

    Notes
    -----
    StatsPerform's open format of handling provides certain additional event attributes,
    which attach additional information to certain events. As of now, these information
    are parsed as a string in the ``qualifier`` column of the returned DataFrame and can
    be transformed to a dict of form ``{attribute: value}``.
    """
    # initialize bin and variables
    events = {}
    team_ids = {"Home": 1.0, "Away": 2.0}
    segments = ["1", "2"]
    for team in team_ids.values():
        events[team] = {segment: pd.DataFrame() for segment in segments}

    # create or check teamsheet objects
    if home_teamsheet is None and away_teamsheet is None:
        teamsheets = read_teamsheets_from_open_data_csv(filepath_events)
        home_teamsheet = teamsheets["Home"]
        away_teamsheet = teamsheets["Away"]
    elif home_teamsheet is None:
        teamsheets = read_teamsheets_from_open_data_csv(filepath_events)
        home_teamsheet = teamsheets["Home"]
    elif away_teamsheet is None:
        teamsheets = read_teamsheets_from_open_data_csv(filepath_events)
        away_teamsheet = teamsheets["Away"]
    else:
        pass
        # potential check

    # parse event data
    with open(str(filepath_events), "r") as f:
        while True:
            line = f.readline()

            # terminate if at end of file
            if len(line) == 0:
                break

            # skip the head
            if line.split(sep=",")[3] == "current_phase":
                continue

            # read single line
            event, team, segment = _read_open_event_csv_single_line(line)

            # insert to bin
            if team:
                team = float(team)
                events[team][segment] = events[team][segment].append(
                    event, ignore_index=True
                )
            else:  # if no clear assignment possible, insert to bins for both teams
                for team in team_ids.values():
                    events[team][segment] = events[team][segment].append(
                        event, ignore_index=True
                    )

    # assembly
    home_ht1 = Events(
        events=events[team_ids["Home"]]["1"],
    )
    home_ht2 = Events(
        events=events[team_ids["Home"]]["2"],
    )
    away_ht1 = Events(
        events=events[team_ids["Home"]]["1"],
    )
    away_ht2 = Events(
        events=events[team_ids["Home"]]["2"],
    )
    data_objects = (
        home_ht1,
        home_ht2,
        away_ht1,
        away_ht2,
        home_teamsheet,
        away_teamsheet,
    )

    return data_objects


def read_open_tracking_data_csv(
    filepath_tracking: Union[str, Path],
    home_teamsheet: Teamsheet = None,
    away_teamsheet: Teamsheet = None,
) -> Tuple[XY, XY, XY, XY, XY, XY, Code, Code, Pitch, Teamsheet, Teamsheet]:
    """Parses an open StatsPerform csv file and extract position data and possession
    codes as well as teamsheets and pitch information.

    Openly published StatsPerform position data (e.g. for the Pro Forum '22) is stored
    in a csv file containing all position data (for both halves) as well as information
    about players, the pitch, and the ball possession. This function provides high-level
    access to StatsPerform data by parsing the csv file.

    Parameters
    ----------
    filepath_tracking: str or pathlib.Path
        Full path to the csv file.
    home_teamsheet: Teamsheet, optional
        Teamsheet-object for the home team used to create link dictionaries of the form
        `links[team][jID] = xID` and  `links[team][pID] = jID`. The links are used to
        map players to a specific xID in the respective XY objects. Should be supplied
        if that order matters. If given as None (default), teamsheet is extracted from
        the Match Information XML file.
    away_teamsheet: Teamsheet, optional
        Teamsheet-object for the away team. If given as None (default), teamsheet is
        extracted from the Match Information XML file.

    Returns
    -------
    data_objects: Tuple[XY, XY, XY, XY, XY, XY, Code, Code, Pitch, Teamsheet, Teamsheet]
        XY-, Code-, Teamsheet-, and Pitch-objects for both teams and both halves. The
        order is (home_ht1, home_ht2, away_ht1, away_ht2, ball_ht1, ball_ht2,
        possession_ht1, possession_ht2, pitch, home_teamsheet, away_teamsheet)
    """
    # parse the csv file into pd.DataFrame
    dat_df = pd.read_csv(str(filepath_tracking))

    # initialize team and ball ids
    team_ids = {"Home": 1.0, "Away": 2.0}
    ball_id = 4

    # check for additional tIDs
    for ID in dat_df["team_id"].unique():
        if not (ID in team_ids.values() or ID == ball_id):
            warnings.warn(f"Team ID {ID} did not match any of the standard IDs!")

    # create or check teamsheet objects
    if home_teamsheet is None and away_teamsheet is None:
        teamsheets = read_teamsheets_from_open_data_csv(filepath_tracking)
        home_teamsheet = teamsheets["Home"]
        away_teamsheet = teamsheets["Away"]
    elif home_teamsheet is None:
        teamsheets = read_teamsheets_from_open_data_csv(filepath_tracking)
        home_teamsheet = teamsheets["Home"]
    elif away_teamsheet is None:
        teamsheets = read_teamsheets_from_open_data_csv(filepath_tracking)
        away_teamsheet = teamsheets["Away"]
    else:
        pass
        # potential check

    # create links
    if "xID" not in home_teamsheet.teamsheet.columns:
        home_teamsheet.add_xIDs()
    if "xID" not in away_teamsheet.teamsheet.columns:
        away_teamsheet.add_xIDs()
    links_jID_to_xID = {}
    links_jID_to_xID["Home"] = home_teamsheet.get_links("jID", "xID")
    links_jID_to_xID["Away"] = away_teamsheet.get_links("jID", "xID")

    # create periods and pitch
    periods, pitch = _create_metadata_from_open_csv_df(dat_df)
    segments = list(periods.keys())

    # infer data shapes
    number_of_players = {team: len(links_jID_to_xID[team]) for team in links_jID_to_xID}
    number_of_frames = {}
    for segment in segments:
        start = periods[segment][0]
        end = periods[segment][1]
        number_of_frames[segment] = end - start + 1

    # bins
    codes = {"possession": {segment: [] for segment in segments}}
    xydata = {
        "Home": {
            segment: np.full(
                [
                    number_of_frames[segment],
                    number_of_players[list(links_jID_to_xID.keys())[0]] * 2,
                ],
                np.nan,
            )
            for segment in periods
        },
        "Away": {
            segment: np.full(
                [
                    number_of_frames[segment],
                    number_of_players[list(links_jID_to_xID.keys())[1]] * 2,
                ],
                np.nan,
            )
            for segment in periods
        },
        "Ball": {
            segment: np.full([number_of_frames[segment], 2], np.nan)
            for segment in periods
        },
    }

    # loop
    for segment in segments:

        # teams
        for team in team_ids:
            team_df = dat_df[dat_df["team_id"] == team_ids[team]]
            for pID in team_df["player_id"].unique():
                # extract player information
                pl_df = team_df[team_df["player_id"] == pID]
                frames = pl_df["frame_count"].values
                x_position = pl_df["pos_x"].values
                y_position = pl_df["pos_y"].values

                # compute appearance of player in segment
                appearance = np.array(
                    [
                        (periods[segment][0] <= frame <= periods[segment][-1])
                        for frame in frames
                    ]
                )
                # check for players that did not play in segment
                if not np.sum(appearance):
                    continue

                # insert player position to bin array
                jrsy = int(pl_df["jersey_no"].values[0])
                x_col = (links_jID_to_xID[team][jrsy] - 1) * 2
                y_col = (links_jID_to_xID[team][jrsy] - 1) * 2 + 1
                start = frames[appearance][0] - periods[segment][0]
                end = frames[appearance][-1] - periods[segment][0] + 1
                xydata[team][segment][start:end, x_col] = x_position[appearance]
                xydata[team][segment][start:end, y_col] = y_position[appearance]

        # ball
        ball_df = dat_df[dat_df["team_id"] == 4]
        frames = ball_df["frame_count"].values
        appearance = np.array(
            [(periods[segment][0] <= frame <= periods[segment][-1]) for frame in frames]
        )
        xydata["Ball"][segment][:, 0] = ball_df["pos_x"].values[appearance]
        xydata["Ball"][segment][:, 1] = ball_df["pos_x"].values[appearance]

        # update codes
        codes["possession"][segment] = ball_df["possession"].values[appearance]

    # create XY objects
    home_ht1 = XY(xy=xydata["Home"][0], framerate=10)
    home_ht2 = XY(xy=xydata["Home"][1], framerate=10)
    away_ht1 = XY(xy=xydata["Away"][0], framerate=10)
    away_ht2 = XY(xy=xydata["Away"][1], framerate=10)
    ball_ht1 = XY(xy=xydata["Ball"][0], framerate=10)
    ball_ht2 = XY(xy=xydata["Ball"][1], framerate=10)

    # create Code objects
    poss_ht1 = Code(
        name="possession",
        code=codes["possession"][0],
        definitions=dict([(team_id, team) for team, team_id in team_ids.items()]),
        framerate=10,
    )
    poss_ht2 = Code(
        name="possession",
        code=codes["possession"][1],
        definitions=dict([(team_id, team) for team, team_id in team_ids.items()]),
        framerate=10,
    )

    data_objects = (
        home_ht1,
        home_ht2,
        away_ht1,
        away_ht2,
        ball_ht1,
        ball_ht2,
        poss_ht1,
        poss_ht2,
        pitch,
        home_teamsheet,
        away_teamsheet,
    )
    return data_objects


# ----------------------------- StatsPerform Format ---------------------------


def _read_tracking_data_txt_single_line(
    line: str,
) -> Tuple[
    int,
    int,
    Dict[str, Dict[str, Tuple[float, float, float]]],
    Dict[str, Union[str, tuple]],
]:
    """Extracts all relevant information from a single line of StatsPerform's tracking
    data .txt file (i.e. one frame of data).

    Parameters
    ----------
    line: str
        One full line from StatsPerform's .txt-file, equals one sample of data.

    Returns
    -------
    gameclock: int
        The gameclock of the current segment in milliseconds.
    segment: int
        The segment identifier.
    positions: Dict[str, Dict[str, Tuple[float, float, float]]]
        Nested dictionary that stores player position information for each team and
        player. Has the form ``positions[team][jID] = (x, y)``.
    ball: Dict[str]
        Dictionary with ball information. Has keys 'position', 'possession' and
        'ballstatus'.
    """
    # bins
    positions = {"Home": {}, "Away": {}, "Other": {}}
    ball = {}

    # read chunks
    chunks = line.split(":")
    time_chunk = chunks[0]
    player_chunks = chunks[1].split(";")

    ball_chunk = None
    if len(chunks) > 2:  # check if ball information exist in chunk
        ball_chunk = chunks[2]

    # time chunk
    # systemclock = time_chunk.split(";")[0]
    # possible check or synchronization step
    timeinfo = time_chunk.split(";")[1].split(",")
    gameclock = int(timeinfo[0])
    segment = int(timeinfo[1])
    # ballstatus = timeinfo[2].split(":")[0] == '0'  # '0' seems to be always the case?

    # player chunks
    for player_chunk in player_chunks:

        # skip final entry of chunk
        if not player_chunk or player_chunk == "\n":
            continue

        # read team
        chunk_data = player_chunk.split(",")
        if chunk_data[0] in ["0", "3"]:
            team = "Home"
        elif chunk_data[0] in ["1", "4"]:
            team = "Away"
        else:
            team = "Other"

        # read IDs
        # pID = chunk_data[1]
        jID = chunk_data[2]

        # read positions
        x, y = map(lambda x: float(x), chunk_data[3:])

        # assign
        positions[team][jID] = (x, y)

    # ball chunk
    if ball_chunk is not None:
        x, y, z = map(lambda x: float(x), ball_chunk.split(";")[0].split(","))
        # ball["position"] = (x, y, z)  # z-coordinate is not yet supported
        ball["position"] = (x, y)

    return gameclock, segment, positions, ball


def _read_time_information_from_tracking_data_txt(
    filepath_tracking: Union[str, Path],
) -> Tuple[Dict, Union[int, None]]:
    """Reads StatsPerform's tracking .txt file and extracts information about the first
    and last frame of periods. Also, a framerate is estimated from the
    gameclock difference between samples.

    Parameters
    ----------
    filepath_tracking: str or pathlib.Path
        Full path to the txt file containing the tracking data.

    Returns
    -------
    periods: Dict
        Dictionary with start and endframes:
        ``periods[segment] = [startframe, endframe]``.
    framerate_est: int or None
        Estimated temporal resolution of data in frames per second/Hertz.
    """

    # bins
    startframes = {}
    endframes = {}
    framerate_est = None

    # read txt file from disk
    file_txt = open(filepath_tracking, "r")

    # loop
    last_gameclock = None
    last_segment = None
    for line in file_txt.readlines():

        # read gameclock and segment
        gameclock, segment, _, _ = _read_tracking_data_txt_single_line(line)

        # update periods
        if segment not in startframes:
            startframes[segment] = gameclock
            if last_gameclock is not None:
                endframes[last_segment] = last_gameclock

        # estimate framerate if desired
        if last_gameclock is not None:
            delta = np.absolute(gameclock - last_gameclock)  # in milliseconds
            if framerate_est is None:
                framerate_est = int(1000 / delta)
            elif framerate_est != int(1000 / delta) and last_segment == segment:
                warnings.warn(
                    f"Framerate estimation yielded diverging results."
                    f"The originally estimated framerate of {framerate_est} Hz did not "
                    f"match the current estimation of {int(1000 / delta)} Hz. This "
                    f"might be caused by missing frame(s) in the position data. "
                    f"Continuing by choosing the latest estimation of "
                    f"{int(1000 / delta)} Hz"
                )
                framerate_est = int(1000 / delta)

        # update variables
        last_gameclock = gameclock
        last_segment = segment

    # update end of final segment
    endframes[last_segment] = last_gameclock

    # assembly
    periods = {
        segment: (startframes[segment], endframes[segment]) for segment in startframes
    }

    # close file
    file_txt.close()

    return periods, framerate_est


def _read_jersey_numbers_from_tracking_data_txt(
    file_location_txt: Union[str, Path],
) -> Tuple[set, set]:
    """Reads StatsPerform's tracking .txt file and extracts unique set of jIDs
    (jerseynumbers) for both teams.

    Parameters
    ----------
    file_location_txt: str or pathlib.Path
        Full path to the txt file containing the tracking data.

    Returns
    -------
    home_jIDs: set
    away_jIDs: set
    """

    # bins
    home_jIDs = set()
    away_jIDs = set()

    # read txt file from disk
    file_txt = open(file_location_txt, "r")

    # loop
    for package in file_txt.readlines():

        # read line
        _, _, positions, _ = _read_tracking_data_txt_single_line(package)

        # extract jersey numbers
        home_jIDs |= set(positions["Home"].keys())
        away_jIDs |= set(positions["Away"].keys())

    # close file
    file_txt.close()

    return home_jIDs, away_jIDs


def read_teamsheets_from_event_data_xml(
    filepath_events: Union[str, Path],
) -> Dict[str, Teamsheet]:
    """Parses the StatsPerform event file and returns two Teamsheet-objects with
    detailed player information for the home and the away team.

    Parameters
    ----------
    filepath_events: str or pathlib.Path
        Full path to the xml file containing the event data.

    Returns
    -------
    teamsheets: Dict[str, Teamsheet]
        Dictionary with teamsheets for the home team and the away team.
    """
    # load event data xml tree into memory
    tree = etree.parse(str(filepath_events))
    root = tree.getroot()

    # initialize teamsheets
    teamsheets = {
        "Home": pd.DataFrame(
            columns=["player", "position", "team_name", "jID", "pID", "tID", "started"]
        ),
        "Away": pd.DataFrame(
            columns=["player", "position", "team_name", "jID", "pID", "tID", "started"]
        ),
    }

    # parse player information
    for team_matchsheet in root.findall("MatchSheet/Team"):

        # skip referees
        if team_matchsheet.attrib["Type"] == "Referees":
            continue

        # read team
        team = team_matchsheet.attrib["Type"][:-4]  # cut 'Team' of e.g. 'HomeTeam'
        tID = team_matchsheet.attrib["IdTeam"]
        team_name = team_matchsheet.attrib["Name"]

        # find players
        players = [
            actor
            for actor in team_matchsheet.findall("Actor")
            if actor.attrib["Occupation"] == "Player"
        ]

        # create teamsheet
        teamsheets[team]["player"] = [
            get_and_convert(player, "NickName", str) for player in players
        ]
        teamsheets[team]["pID"] = [
            get_and_convert(player, "IdActor", int) for player in players
        ]
        teamsheets[team]["jID"] = [
            get_and_convert(player, "JerseyNumber", int) for player in players
        ]
        teamsheets[team]["position"] = [
            get_and_convert(player, "Position", str) for player in players
        ]
        teamsheets[team]["started"] = [
            get_and_convert(player, "IsStarter", bool) for player in players
        ]
        teamsheets[team]["tID"] = tID
        teamsheets[team]["team_name"] = team_name

    # create teamsheet objects
    for team in teamsheets:
        teamsheets[team] = Teamsheet(teamsheets[team])

    return teamsheets


def read_teamsheets_from_tracking_data_txt(
    filepath_tracking: Union[str, Path],
) -> Dict[str, Teamsheet]:
    """Parses the StatsPerform tracking file and returns two simple Teamsheet-objects
    containing only two columns "player" and "jID" for the home and the away team.

    Parameters
    ----------
    filepath_tracking: str or pathlib.Path
        Full path to the txt file containing the tracking data.

    Returns
    -------
    teamsheets: Dict[str, Teamsheet]
        Dictionary with teamsheets for the home team and the away team.
    """
    # create list of jIDs
    homejrsy, awayjrsy = _read_jersey_numbers_from_tracking_data_txt(filepath_tracking)
    homejrsy = list(homejrsy)
    awayjrsy = list(awayjrsy)
    homejrsy.sort()
    awayjrsy.sort()
    jIDs = {
        "Home": homejrsy,
        "Away": awayjrsy,
    }

    # create teamsheets
    teamsheets = {
        "Home": pd.DataFrame(columns=["player", "jID"]),
        "Away": pd.DataFrame(columns=["player", "jID"]),
    }
    for team in teamsheets:
        teamsheets[team]["player"] = [f"player {i}" for i in range(len(jIDs[team]))]
        teamsheets[team]["jID"] = [int(jID) for jID in jIDs[team]]

    # create teamsheet objects
    for team in teamsheets:
        teamsheets[team] = Teamsheet(teamsheets[team])

    return teamsheets


def read_event_data_xml(
    filepath_events: Union[str, Path],
    home_teamsheet: Teamsheet = None,
    away_teamsheet: Teamsheet = None,
) -> Tuple[Events, Events, Events, Events, Pitch, Teamsheet, Teamsheet]:
    """Parses a StatsPerform .xml file and extracts event data and pitch information.

    This function provides a high-level access to the StatsPerform match events xml file
    and returns Events objects for both teams and information about the pitch.

    Parameters
    ----------
    filepath_events: str or pathlib.Path
        Full path to the xml file containing the event data.
    home_teamsheet: Teamsheet, optional
        Teamsheet-object for the home team used to create link dictionaries of the form
        `links[team][jID] = xID` and  `links[team][pID] = jID`. The links are used to
        map players to a specific xID in the respective XY objects. Should be supplied
        if that order matters. If given as None (default), teamsheet is extracted from
        the Match Information XML file.
    away_teamsheet: Teamsheet, optional
        Teamsheet-object for the away team. If given as None (default), teamsheet is
        extracted from the Match Information XML file.

    Returns
    -------
    data_objects: Tuple[Events, Events, Events, Events, Pitch]
        Events-objects for both teams and both halves, pitch information, and
        teamsheets. The order is (home_ht1, home_ht2, away_ht1, away_ht2, pitch,
        home_teamsheet, away_teamsheet).
    """
    # load xml tree into memory
    tree = etree.parse(str(filepath_events))
    root = tree.getroot()

    # create bins, read segments, and assign teams
    columns = [
        "eID",
        "gameclock",
        "pID",
        "minute",
        "second",
        "at_x",
        "at_y",
        "to_x",
        "to_y",
        "qualifier",
    ]
    segments = [
        f"HT{get_and_convert(period.attrib, 'IdHalf', str)}"
        for period in root.findall("Events/EventsHalf")
    ]
    teams = ["Home", "Away"]

    # create or check teamsheet objects
    if home_teamsheet is None and away_teamsheet is None:
        teamsheets = read_teamsheets_from_event_data_xml(filepath_events)
        home_teamsheet = teamsheets["Home"]
        away_teamsheet = teamsheets["Away"]
    elif home_teamsheet is None:
        teamsheets = read_teamsheets_from_event_data_xml(filepath_events)
        home_teamsheet = teamsheets["Home"]
    elif away_teamsheet is None:
        teamsheets = read_teamsheets_from_event_data_xml(filepath_events)
        away_teamsheet = teamsheets["Away"]
    else:
        pass
        # potential check

    # create links between pIDs and team
    links_pID_to_team = {}
    links_pID_to_team["Home"] = {pID: "Home" for pID in home_teamsheet["pID"]}
    links_pID_to_team["Away"] = {pID: "Away" for pID in away_teamsheet["pID"]}

    # bins
    event_lists = {
        team: {segment: {col: [] for col in columns} for segment in segments}
        for team in teams
    }

    # loop over events
    for half in root.findall("Events/EventsHalf"):
        # get segment information
        period = get_and_convert(half.attrib, "IdHalf", str)
        segment = "HT" + str(period)
        for event in half.findall("Event"):
            # read pID
            pID = get_and_convert(event.attrib, "IdActor1", int)

            # assign team
            team = get_and_convert(links_pID_to_team, pID, str)

            # create list of either a single team or both teams if no clear assignment
            if team == "None":
                teams_assigned = teams  # add to both teams
            else:
                teams_assigned = [team]  # only add to one team

            # identifier
            eID = get_and_convert(event.attrib, "EventName", str)
            for team in teams_assigned:
                event_lists[team][segment]["eID"].append(eID)
                event_lists[team][segment]["pID"].append(pID)

            # relative time
            gameclock = get_and_convert(event.attrib, "Time", int) / 1000
            minute = np.floor(gameclock / 60)
            second = np.floor(gameclock - minute * 60)
            for team in teams_assigned:
                event_lists[team][segment]["gameclock"].append(gameclock)
                event_lists[team][segment]["minute"].append(minute)
                event_lists[team][segment]["second"].append(second)

            # location
            at_x = get_and_convert(event.attrib, "LocationX", float)
            at_y = get_and_convert(event.attrib, "LocationY", float)
            to_x = get_and_convert(event.attrib, "TargetX", float)
            to_y = get_and_convert(event.attrib, "TargetY", float)
            for team in teams_assigned:
                event_lists[team][segment]["at_x"].append(at_x)
                event_lists[team][segment]["at_y"].append(at_y)
                event_lists[team][segment]["to_x"].append(to_x)
                event_lists[team][segment]["to_y"].append(to_y)

            # qualifier
            qual_dict = {}
            for qual_id in event.attrib:
                qual_value = event.attrib.get(qual_id)
                qual_dict[qual_id] = qual_value
            for team in teams_assigned:
                event_lists[team][segment]["qualifier"].append(str(qual_dict))

    # create pitch
    length = get_and_convert(root.attrib, "FieldLength", int) / 100
    width = get_and_convert(root.attrib, "FieldWidth", int) / 100
    pitch = Pitch.from_template(
        "statsperform_event",
        length=length,
        width=width,
        sport="football",
    )

    # assembly
    home_ht1 = Events(
        events=pd.DataFrame(data=event_lists["Home"]["HT1"]),
    )
    home_ht2 = Events(
        events=pd.DataFrame(data=event_lists["Home"]["HT2"]),
    )
    away_ht1 = Events(
        events=pd.DataFrame(data=event_lists["Away"]["HT1"]),
    )
    away_ht2 = Events(
        events=pd.DataFrame(data=event_lists["Away"]["HT2"]),
    )

    data_objects = (
        home_ht1,
        home_ht2,
        away_ht1,
        away_ht2,
        pitch,
        home_teamsheet,
        away_teamsheet,
    )

    return data_objects


def read_tracking_data_txt(
    filepath_tracking: Union[str, Path],
    home_teamsheet: Teamsheet = None,
    away_teamsheet: Teamsheet = None,
) -> Tuple[XY, XY, XY, XY, XY, XY, Teamsheet, Teamsheet]:
    """Parses a StatsPerform .txt file and extracts position data and teamsheets.

     Internal StatsPerform position data is stored as a .txt file containing all
     position data (for both halves). This function provides high-level access to
     StatsPerform data by parsing the txt file. Since no information about framerate is
     delivered in the data itself, it is estimated from time difference between
     individual frames. Teamsheets are extracted from the event data, if filepath_events
     is provided. Otherwise, a simple Teamsheet-objects is inferred from the tracking
     data.

    Parameters
    ----------
    filepath_tracking: str or pathlib.Path
        Full path to the txt file containing the tracking data.
    filepath_events: str or pathlib.Path, optional
        Full path to the xml file containing the event data. Is used to create detailed
        Teamsheet-objects for both teams. If not provided, teamsheet objects with
        columns only containing player, pID, and jID are inferred from the tracking
        data.
    home_teamsheet: Teamsheet, optional
        Teamsheet-object for the home team used to create link dictionaries of the form
        `links[team][jID] = xID` and  `links[team][pID] = jID`. The links are used to
        map players to a specific xID in the respective XY objects. Should be supplied
        if that order matters. If given as None (default), teamsheet is extracted from
        the Match Information XML file.
    away_teamsheet: Teamsheet, optional
        Teamsheet-object for the away team. If given as None (default), teamsheet is
        extracted from the Match Information XML file.

    Returns
    -------
    data_objects: Tuple[XY, XY, XY, XY, XY, XY, Teamsheet, Teamsheet]
        XY-objects for both teams and both halves. The order is (home_ht1, home_ht2,
        away_ht1, away_ht2, ball_ht1, ball_ht2, home_teamsheet, away_teamsheet).
    """
    # parse txt file for periods and estimate framerate if not contained in filepath
    periods, framerate_est = _read_time_information_from_tracking_data_txt(
        filepath_tracking
    )
    segments = list(periods.keys())

    # create or check teamsheet objects
    if home_teamsheet is None and away_teamsheet is None:
        teamsheets = read_teamsheets_from_tracking_data_txt(filepath_tracking)
        home_teamsheet = teamsheets["Home"]
        away_teamsheet = teamsheets["Away"]
    elif home_teamsheet is None:
        teamsheets = read_teamsheets_from_tracking_data_txt(filepath_tracking)
        home_teamsheet = teamsheets["Home"]
    elif away_teamsheet is None:
        teamsheets = read_teamsheets_from_tracking_data_txt(filepath_tracking)
        away_teamsheet = teamsheets["Away"]
    else:
        pass
        # potential check

    # create links
    if "xID" not in home_teamsheet.teamsheet.columns:
        home_teamsheet.add_xIDs()
    if "xID" not in away_teamsheet.teamsheet.columns:
        away_teamsheet.add_xIDs()
    links_jID_to_xID = {}
    links_jID_to_xID["Home"] = home_teamsheet.get_links("jID", "xID")
    links_jID_to_xID["Away"] = away_teamsheet.get_links("jID", "xID")

    # infer data array shapes
    number_of_home_players = max(links_jID_to_xID["Home"].values()) + 1
    number_of_away_players = max(links_jID_to_xID["Away"].values()) + 1
    number_of_frames = {}
    for segment in segments:
        number_of_frames[segment] = (
            int((periods[segment][1] - periods[segment][0]) / 1000 * framerate_est) + 1
        )

    # bins
    xydata = {}
    xydata["Home"] = {
        segment: np.full(
            [number_of_frames[segment], number_of_home_players * 2], np.nan
        )
        for segment in segments
    }
    xydata["Away"] = {
        segment: np.full(
            [number_of_frames[segment], number_of_away_players * 2], np.nan
        )
        for segment in segments
    }
    xydata["Ball"] = {
        segment: np.full([number_of_frames[segment], 2], np.nan) for segment in segments
    }

    # read txt file from disk
    with open(filepath_tracking, "r") as f:
        tracking_data_lines = f.readlines()

    # loop
    for package in tracking_data_lines:

        # read line to get gameclock, player positions and ball info
        (
            gameclock,
            segment,
            positions,
            ball,
        ) = _read_tracking_data_txt_single_line(package)

        # check if frame is in any segment
        if segment is None:
            # skip line if not
            continue
        else:
            # otherwise calculate relative frame (in respective segment)
            frame_rel = int((gameclock - periods[segment][0]) / 1000 * framerate_est)

        # insert (x,y)-data into np.array
        for team in ["Home", "Away"]:
            for jID in positions[team].keys():

                # map jersey number to array index and infer respective columns
                x_col = (links_jID_to_xID[team][int(jID)] - 1) * 2
                y_col = (links_jID_to_xID[team][int(jID)] - 1) * 2 + 1
                xydata[team][segment][frame_rel, x_col] = positions[team][jID][0]
                xydata[team][segment][frame_rel, y_col] = positions[team][jID][1]

        # get ball data
        xydata["Ball"][segment][frame_rel] = ball.get("position", np.nan)

    # create XY objects
    home_ht1 = XY(xy=xydata["Home"][1], framerate=framerate_est)
    home_ht2 = XY(xy=xydata["Home"][2], framerate=framerate_est)
    away_ht1 = XY(xy=xydata["Away"][1], framerate=framerate_est)
    away_ht2 = XY(xy=xydata["Away"][2], framerate=framerate_est)
    ball_ht1 = XY(xy=xydata["Ball"][1], framerate=framerate_est)
    ball_ht2 = XY(xy=xydata["Ball"][2], framerate=framerate_est)

    data_objects = (
        home_ht1,
        home_ht2,
        away_ht1,
        away_ht2,
        ball_ht1,
        ball_ht2,
        home_teamsheet,
        away_teamsheet,
    )

    return data_objects


def read_event_data_from_url(
    url: str,
    home_teamsheet: Teamsheet = None,
    away_teamsheet: Teamsheet = None,
) -> Tuple[Events, Events, Events, Events, Pitch, Teamsheet, Teamsheet]:
    """Reads a URL containing a StatsPerform events csv file and extracts the stored
    event data, pitch information, and teamsheets.

    The event data from the URL is downloaded into a temporary file stored in the
    repository's internal root ``.data``-folder and removed afterwards.

    Parameters
    ----------
    url: str
        URL to the xml file containing the event data.
    home_teamsheet: Teamsheet, optional
        Teamsheet-object for the home team used to create link dictionaries of the form
        `links[team][jID] = xID` and  `links[team][pID] = jID`. The links are used to
        map players to a specific xID in the respective XY objects. Should be supplied
        if that order matters. If given as None (default), teamsheet is extracted from
        the Match Information XML file.
    away_teamsheet: Teamsheet, optional
        Teamsheet-object for the away team. If given as None (default), teamsheet is
        extracted from the Match Information XML file.

    Returns
    -------
    data_objects: Tuple[Events, Events, Events, Events, Pitch]
        Events-objects for both teams and both halves, pitch information, and
        teamsheets. The order is (home_ht1, home_ht2, away_ht1, away_ht2, pitch,
        home_teamsheet, away_teamsheet).
    """
    data_dir = os.path.join(DATA_DIR, "statsperform")
    if not os.path.isdir(data_dir):
        os.makedirs(data_dir, exist_ok=True)
    temp_file = os.path.join(data_dir, "events_temp.xml")
    with open(temp_file, "wb") as binary_file:
        binary_file.write(download_from_url(url))
    (
        home_ht1,
        home_ht2,
        away_ht1,
        away_ht2,
        pitch,
        home_teamsheet,
        away_teamsheet,
    ) = read_event_data_xml(
        filepath_events=os.path.join(data_dir, temp_file),
        home_teamsheet=home_teamsheet,
        away_teamsheet=away_teamsheet,
    )
    data_objects = (
        home_ht1,
        home_ht2,
        away_ht1,
        away_ht2,
        pitch,
        home_teamsheet,
        away_teamsheet,
    )
    os.remove(os.path.join(data_dir, temp_file))
    return data_objects


def read_tracking_data_from_url(
    url: str,
    home_teamsheet: Teamsheet = None,
    away_teamsheet: Teamsheet = None,
) -> Tuple[XY, XY, XY, XY, XY, XY, Teamsheet, Teamsheet]:
    """Reads a URL from the StatsPerform API (StatsEdgeViewer) containing a tracking
    data txt file and extracts position data and teamsheets.

    The tracking data from the URL is downloaded into a temporary file stored in the
    repository's internal root ``.data``-folder and removed afterwards.

    Parameters
    ----------
    url: str or pathlib.Path
        URL to the txt file containing the tracking data.
    home_teamsheet: Teamsheet, optional
        Teamsheet-object for the home team used to create link dictionaries of the form
        `links[team][jID] = xID` and  `links[team][pID] = jID`. The links are used to
        map players to a specific xID in the respective XY objects. Should be supplied
        if that order matters. If given as None (default), teamsheet is extracted from
        the Match Information XML file.
    away_teamsheet: Teamsheet, optional
        Teamsheet-object for the away team. If given as None (default), teamsheet is
        extracted from the Match Information XML file.

    Returns
    -------
    data_objects: Tuple[XY, XY, XY, XY, XY, XY, Teamsheet, Teamsheet]
        XY-objects for both teams and both halves. The order is (home_ht1, home_ht2,
        away_ht1, away_ht2, ball_ht1, ball_ht2, home_teamsheet, away_teamsheet).
    """
    data_dir = os.path.join(DATA_DIR, "statsperform")
    if not os.path.isdir(data_dir):
        os.makedirs(data_dir, exist_ok=True)
    temp_file = os.path.join(data_dir, "tracking_temp.txt")
    with open(temp_file, "wb") as binary_file:
        binary_file.write(download_from_url(url))
    (
        home_ht1,
        home_ht2,
        away_ht1,
        away_ht2,
        ball_ht1,
        ball_ht2,
    ) = read_tracking_data_txt(
        filepath_tracking=os.path.join(data_dir, temp_file),
        home_teamsheet=home_teamsheet,
        away_teamsheet=away_teamsheet,
    )
    data_objects = (
        home_ht1,
        home_ht2,
        away_ht1,
        away_ht2,
        ball_ht1,
        ball_ht2,
        home_teamsheet,
        away_teamsheet,
    )
    os.remove(os.path.join(data_dir, temp_file))
    return data_objects
