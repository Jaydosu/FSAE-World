"""
get historical competition data for every team

"""

import requests
from bs4 import BeautifulSoup
import json

def scrape_events():
    """
    Fetch and parse event options from a remote HTML page and write them to 'events.json'.
    This function performs an HTTP GET to the URL referenced by `example2`, parses the response
    HTML with BeautifulSoup, and processes all <option> elements with id="event". For each such
    <option> it extracts:
    - event_id: int(option['value'])
    - region: option['data-region']
    - class: mapped from option['data-class'] using {"1": "CV", "2": "EV", "3": "DC"}, defaults to "Unknown"
    - date and name: parsed from the option text which is expected to be in the form "DATE - NAME"
    The collected events are assembled into a dict keyed by event_id with values of the form:
    {
        "region": <str>,
        "class": <str>,
        "date": <str>,
        "name": <str>
    Events are sorted by the extracted date string in descending order and the resulting mapping
    is written as pretty-printed JSON to "events.json" in the current working directory.
    Returns:
        None
    Raises:
        requests.RequestException: if the HTTP request fails.
        ValueError, IndexError: if expected attributes or the "DATE - NAME" text format are missing or malformed.
    Notes:
        - Date sorting is performed on the raw date strings (lexicographic); ensure dates are in a
          format that sorts correctly if chronological order is required.
        - This function has side effects (network access and file I/O).
    """
    example2 = "https://www.fs-world.org/ranking/ev/404"
    response2 = requests.get(example2)
    soup2 = BeautifulSoup(response2.content, "html.parser")

    # Get all Options in the select tag if it has class data-class
    options = soup2.find_all("option")

    events = {}
    map_class_to_name = {
        "1": "CV",
        "2": "EV",
        "3": "DC"}

    for option in options:
        if option.get("id") != "event":
            continue
        event_id = int(option.get("value"))
        event_region = option.get("data-region")
        event_class = option.get("data-class")
        event_class = map_class_to_name.get(event_class, "Unknown")
        option_value = option.text.strip()
        event_date = option_value.split(" - ")[0].strip()
        event_name = option_value.split(" - ")[1].strip()

        events[event_id] = {
            "region": event_region,
            "class": event_class,
            "date": event_date,
            "name": event_name,
        }

    # Sort events by date descending
    events = dict(sorted(events.items(), key=lambda item: item[1]["date"], reverse=True))

    with open("events.json", "w") as f:
        json.dump(events, f, indent=4)

def scrape_team(id, checknew=False):
    """Scrape competition results for a single university/team from fs-world.org.
    This function requests the university page for the given id and attempts to
    retrieve historical competition tables for both combustion (CV) and electric (EV)
    classes (endpoints: /cv and /ev). It parses the first HTML table found on each
    successful page, expects 16 columns per result row (header is skipped), maps
    columns to known result fields, cross-references the event by name and date
    against the global `events` mapping, and builds result entries keyed by
    "{event_id}_{uni_id}".
    Parameters
    - id (int | str): University/team identifier used to form the URL
        "https://www.fs-world.org/university/{id}". Treated as uni_id in output.
    - checknew (bool): If False (default), the function will first check the
        global `e_results` and skip scraping if any existing result entry contains
        this uni_id. If True, that initial skip is disabled and scraping proceeds.
    Globals used
    - e_results (dict): Existing results, used to skip duplicates. Expected to be a
        mapping of result_id -> result info.
    - events (dict): Mapping of event_id -> { "name": ..., "date": ... } used to
        find the numeric event_id for each scraped result.
    - requests, BeautifulSoup: HTTP and HTML parsing libraries used internally.
    Return value
    - list of dict: Each element is a single-key dict mapping result_id (str,
        formatted as "{event_id}_{uni_id}") to a result dict:
                "uni_id": <int|str>,
                "class": "CV" | "EV",
                    BP, CM, ED, SP, DV SP, AC, DV AC, AX, EN, EF, PE, total_points
                ]  # all numeric values are converted to float (total_points included)
    Behavior and notes
    - Only the first <table> on each page is considered. Rows with != 16 <td>
        cells are ignored.
    - Column mapping expected (index -> field): 0:name, 1:date, 2:WRL#, 3:event_rank,
        4:total_points, 5:BP, 6:CM, 7:ED, 8:SP, 9:DV SP, 10:AC, 11:DV AC, 12:AX,
        13:EN, 14:EF, 15:PE.
    - If a scraped event's name+date cannot be matched in `events`, that row is
        skipped (a message is printed).
    - If the constructed result_id already exists in `e_results`, that result is
        skipped.
    - The function prints informative messages about skips, matches, and missing
        events, and returns the list of new result entries (empty list if none found
        or skipped).
    - Numeric parsing errors (e.g., invalid float/int conversion) will raise the
        corresponding exceptions (not explicitly handled).
    """

    
    url = f"https://www.fs-world.org/university/{id}"
    uni_id = id

    if checknew == False:
        # Look for existing results for this team, skip if found
        if any(str(uni_id) == str(result["uni_id"]) for result in e_results.values()):
            print(f"Results for team ID {uni_id} already exist, skipping.")
            return []
    
    # Teams can have CV and EV
    # Try to make a request for /cv and /ev
    # If 404, skip
    map_col_to_data = {
        0: "name",
        1: "date",
        2: "WRL#",
        3: "event_rank",
        4: "total_points",
        5: "BP",
        6: "CM",
        7: "ED",
        8: "SP",
        9: "DV SP",
        10: "AC",
        11: "DV AC",
        12: "AX",
        13: "EN",
        14: "EF",
        15: "PE"
    }

    """
    Result format:
    {
        "result_id": {
            "uni_id": <int>,
            "event_id": <int>,
            "class": <str>,  # "CV" or "EV" or "DC"
            "event_rank": <int>,
            "results": [BP, CM, ED, SP, DV SP, AC, DV AC, AX, EN, EF, PE, total_points]
    }

    result_id will be the unique key for each result entry formatted as: "eventid_uniid"
    """
    results = [] # List of dicts to be built then written into results.json
    

    responses = []
    response_cv = requests.get(f"{url}/cv")
    response_ev = requests.get(f"{url}/ev")

    if response_cv.status_code == 200:
        responses.append(response_cv)
    if response_ev.status_code == 200:
        responses.append(response_ev)

    for resp in responses:
        soup = BeautifulSoup(resp.content, "html.parser")

        # Find the table with historical competition data and then parse it
        table = soup.find("table")
        if table:
            rows = table.find_all("tr")
            for row in rows[1:]:  # Skip header row
                cols = row.find_all("td")
                if len(cols) == 16:
                    data = {map_col_to_data[i]: cols[i].text.strip() for i in range(16)}

                    # Given we know the event name and date, we can cross-reference 
                    # with events.json and find the event_id
                    name = data["name"]
                    date = data["date"]

                    event_id = next((eid for eid, info in events.items()
                                     if info["name"] == name and info["date"] == date), None)
                    event_id = int(event_id) if event_id else None

                    if event_id:
                        # If eventid_uniid already exists in e_results, skip
                        if e_results.get(f"{event_id}_{uni_id}"):
                            print(f"Result for event ID {event_id} and uni ID {uni_id} already exists, skipping.")
                            continue

                        print(f"Found event ID {event_id} for {name} on {date}")
                        result_id = f"{event_id}_{uni_id}"
                        result = {
                            "uni_id": uni_id,
                            "event_id": event_id,
                            "class": "CV" if resp == response_cv else "EV",
                            "event_rank": int(data["event_rank"]),
                            "results": [
                                float(data["BP"]),
                                float(data["CM"]),
                                float(data["ED"]),
                                float(data["SP"]),
                                float(data["DV SP"]),
                                float(data["AC"]),
                                float(data["DV AC"]),
                                float(data["AX"]),
                                float(data["EN"]),
                                float(data["EF"]),
                                float(data["PE"]),
                                float(data["total_points"])
                            ]}
                        results.append({result_id: result})
                    else:
                        print(f"No matching event found for {name} on {date}")

    return results

# Load teams data
with open("teams.json", "r", encoding="utf-8") as f:
    teams = json.load(f)
    # Convert team ids to integers
    teams = {int(k): v for k, v in teams.items()}

# Load results data
with open("results.json", "r") as f:
    e_results = json.load(f)

# Load events data
with open("events.json", "r") as f:
    events = json.load(f)

def scrape_next_n(n):
    """Scrape the next n team entries after the highest recorded uni_id and persist results.
    This function inspects the global `e_results` mapping to determine the largest
    existing "uni_id" value, then attempts to scrape data for the next n integer
    IDs (biggest_id + 1 through biggest_id + n). For each candidate ID:
    - If the ID exists in the global `teams` mapping, `scrape_team(id)` is called.
        Each result returned by `scrape_team` is merged into the global `e_results`.
    - If the ID is not present in `teams`, the ID is skipped.
    After processing the ten IDs, the updated `e_results` is written to "results.json"
    using `json.dump(..., indent=4)`.
    Inputs: 
    - n: int - The number of team IDs to attempt to scrape.
    Side effects:
    - Mutates the global `e_results` mapping.
    - Calls the global function `scrape_team`.
    - Prints progress and skip messages to stdout.
    - Writes the updated results to the file "results.json".
    Preconditions:
    - `e_results` is a dict-like mapping whose values are mappings containing the
        key "uni_id" (an integer).
    - `teams` is a dict-like mapping of integer team IDs to team metadata (e.g., names).
    - `scrape_team(id)` is callable and returns an iterable of mappings suitable for
        updating `e_results`.
    - The `json` module is available for serialization.
    Exceptions:
    - File I/O errors when writing "results.json" may be raised.
    - `KeyError`, `TypeError`, or `ValueError` may occur if the global structures
        or return values do not have the expected shapes.
    - Any exceptions raised by `scrape_team` will propagate.
    Return:
    - None
    """
    
    # Look in results to see biggest uni_id we have
    existing_ids = {result["uni_id"] for result in e_results.values()}
    biggest_id = max(existing_ids) if existing_ids else 0

    i = biggest_id + 1
    count = 0
    max_team_id = max(teams.keys()) if teams else biggest_id

    while count < n and i <= max_team_id:
        if i in teams:
            # Add a random time delay between requests to avoid rate limiting
            import random, time

            delay = random.uniform(1, 10)
            print(f"Waiting for {delay:.2f} seconds before starting scraping...")
            time.sleep(delay)

            print(f"Scraping team ID {i} - {teams[i]}")
            new_results = scrape_team(i)
            for res in new_results:
                e_results.update(res)
            count += 1
        else:
            print(f"Team ID {i} not found in teams.json, skipping.")
        i += 1

    if count < n:
        print(f"Reached end of known team IDs (max {max_team_id}). Scraped {count} of requested {n}.")

    # Write updated results back to results.json
    with open("results.json", "w") as f:
        json.dump(e_results, f, indent=4)

scrape_next_n(50)
print("Latest scrape complete.\nLatest team ID scraped: {} - {}".format(max(result["uni_id"] for result in e_results.values()), teams[max(result["uni_id"] for result in e_results.values())]))
print("Size of results:", len(e_results))