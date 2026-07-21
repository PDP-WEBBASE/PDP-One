from .hezareh import HezarehParser
from .parsnamad import ParsNamadParser


def parser_for(connector_key: str, base_url: str, declared_type: str):
    if connector_key in {"hezareh_tenders", "hezareh_inquiries"}:
        return HezarehParser(base_url=base_url, declared_type=declared_type)
    if connector_key in {"parsnamad_tenders", "parsnamad_inquiries"}:
        return ParsNamadParser(base_url=base_url, declared_type=declared_type)
    raise ValueError(f"No parser is registered for connector: {connector_key}")
