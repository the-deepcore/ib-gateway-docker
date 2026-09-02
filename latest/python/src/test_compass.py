import json

import httpx

from dotenv import dotenv_values

from dateutil import parser

from dotenv import dotenv_values


config = dotenv_values("/tmp/secrets/.env")

BASE_URL = config['COMPASS_URL']
HEADERS = {"access_token": config['COMPASS_TOKEN']}
DATE_FORMAT = "%Y-%m-%dT%H:%M:%SZ"
INDEX = "MXDSLSSI"

THEDEEPCORE_API_URL = config['THEDEEPCORE_URL']
THEDEEPCORE_ACCESS_TOKEN = config['THEDEEPCORE_TOKEN']


def _url(*parts: str) -> str:
    return "/".join([BASE_URL.rstrip("/"), "indexes", *parts])


def _raise_for_status(response: httpx.Response, expected: int) -> None:
    if response.status_code == expected:
        return
    msg = f"HTTP {response.status_code} – {response.text}"
    raise RuntimeError(msg)


def list_allocations(client: httpx.Client, index: str) -> list[dict]:
    """Return all allocation records for the given index, handling pagination."""
    url = _url(index, "allocations")
    records = []
    while url is not None:
        response = client.get(url)
        _raise_for_status(response, httpx.codes.OK)
        body = response.json()
        records.extend(body.get("data", []))
        url = body.get("next_url")
    return records


def post_allocation(
    client: httpx.Client,
    index: str,
    date: str,
    weights: dict[str, float],
) -> dict:
    """
    Create a new allocation.

    Parameters
    ----------
    date:
        ISO-8601 datetime string, e.g. "2024-01-15T00:00:00Z".
    weights:
        Mapping of underlying ticker → weight, e.g. {"AAPL": 0.5, "MSFT": 0.5}.
    """
    payload = {
        "date": date,
        "weights": [{"underlying": k, "value": v} for k, v in weights.items()],
    }
    response = client.post(
        _url(index, "allocations"),
        content=json.dumps(payload),
    )
    _raise_for_status(response, httpx.codes.CREATED)
    return response.json()["data"]


def delete_allocation(client: httpx.Client, index: str, date: str) -> None:
    """
    Delete the allocation for the given date.

    Parameters
    ----------
    date:
        ISO-8601 datetime string, e.g. "2024-01-15T00:00:00Z".
    """
    response = client.delete(_url(index, "allocations", date))
    _raise_for_status(response, httpx.codes.OK)


def parse_date(date: str):
    """
    Returns a date with format "YYYY-MM-DD"
    """
    date_str = parser.parse(date)
    y = date_str.strftime("%Y")
    m = date_str.strftime("%m")
    d = date_str.strftime("%d")
    return "-".join([y,m,d])


def get_trades(client: httpx.Client):
    """
    Get trades weights for sugar indices from TheDeepcore
    """
    response = client.get(
        THEDEEPCORE_API_URL,
        headers={'Content-Type':'application/json', 'Authorization': 'Bearer {}'.format(THEDEEPCORE_ACCESS_TOKEN)}
    )
    _raise_for_status(response, httpx.codes.OK)
    return response.json()["market_intelligence_trades"]


def main() -> None:
    with httpx.Client(headers=HEADERS) as client:

        dates = []

        try:
            # 1. List existing allocations
            print("=== Listing allocations ===")
            allocations = list_allocations(client, INDEX)
            for alloc in allocations:
                date = parse_date(alloc['date'])
                dates.append(date)

        except:
            print("No allocations found")

        try:
            # 2. Create new allocations
            print("=== Create allocations ===")
            response = get_trades(client)
            for item in response:
                d = parse_date(item['date'])
                if d not in dates:
                    date = f"{d}T00:00:00Z"
                    weights = {"MXSUGAFE": item['trade']}
                    created = post_allocation(client, INDEX, date, weights)
                    print(created)
        except:
            print("Could not create allocations")
            

if __name__ == "__main__":
    main()
