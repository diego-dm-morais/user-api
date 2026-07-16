import hashlib
import hmac

from fastapi import Depends, Header, HTTPException, status

from user_api.config import Settings, get_settings

_GENERIC_401_DETAIL = "Invalid or missing API key"


def _matches_any_hash(candidate_hash: str, valid_hashes: frozenset[str]) -> bool:
    # Iterate over every hash (no early return) so timing does not leak
    # whether the key matched the 1st or the Nth configured hash.
    matched = False
    for valid_hash in valid_hashes:
        if hmac.compare_digest(candidate_hash, valid_hash):
            matched = True
    return matched


async def verify_api_key(
    x_api_key: str | None = Header(default=None),
    settings: Settings = Depends(get_settings),
) -> None:
    """FastAPI dependency enforcing FR-014 / ADR-004.

    Returns the same generic 401 for a missing key and for a malformed/unknown
    key (SC-005) — never reveals which case occurred.
    """
    if not x_api_key:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=_GENERIC_401_DETAIL)

    candidate_hash = hashlib.sha256(x_api_key.encode("utf-8")).hexdigest()
    if not _matches_any_hash(candidate_hash, settings.api_key_hash_set):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=_GENERIC_401_DETAIL)
