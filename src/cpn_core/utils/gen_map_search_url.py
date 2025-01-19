from typing import LiteralString
from urllib.parse import quote_plus

GOOGLE_MAPS_QUERY_STRING: LiteralString = "https://www.google.com/maps/search/{query}"


def gen_map_search_url(location: str) -> str:
    return GOOGLE_MAPS_QUERY_STRING.format(query=quote_plus(location))
