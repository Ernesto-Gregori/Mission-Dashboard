"""Expiry del token OAuth se persiste y vuelve a dejar creds.valid en falso."""
from datetime import datetime, timedelta, timezone


def _past_iso() -> str:
    dt = datetime.now(timezone.utc) - timedelta(hours=3)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _future_iso() -> str:
    dt = datetime.now(timezone.utc) + timedelta(hours=3)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _token(**extra):
    base = {
        "token": "ya29.access",
        "refresh_token": "1//refresh",
        "token_uri": "https://oauth2.googleapis.com/token",
        "client_id": "cid",
        "client_secret": "sec",
        "scopes": ["https://www.googleapis.com/auth/calendar"],
    }
    base.update(extra)
    return base


def test_creds_restauran_expiry_pasado_y_no_son_validas():
    from app.google_fit import _creds_from_token_dict

    creds = _creds_from_token_dict(_token(expiry=_past_iso()))
    assert creds is not None
    assert creds.expiry is not None
    assert creds.expired is True
    assert creds.valid is False


def test_creds_con_expiry_futuro_siguen_validas():
    from app.google_fit import _creds_from_token_dict

    creds = _creds_from_token_dict(_token(expiry=_future_iso()))
    assert creds.expired is False
    assert creds.valid is True


def test_stamp_expiry_guarda_iso_aunque_venga_datetime():
    from app.google_fit import _creds_from_token_dict, _stamp_expiry

    naive = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=3)
    stored = _stamp_expiry(_token(expiry=naive))
    assert isinstance(stored["expiry"], str)
    assert stored["expiry"].endswith("Z")
    creds = _creds_from_token_dict(stored)
    assert creds.expired is True
