"""Unit tests for SharePoint Online SP site group expansion helpers.

Covers _parse_sp_group_member, _email_from_membership_login, and the cursor
migration path for tracked_sp_groups.
"""

from unittest.mock import MagicMock

from connector_context.platform.sources.sharepoint_online.source import (
    EVERYONE_EXCEPT_EXTERNAL_PRINCIPAL,
    SharePointOnlineBase,
)

# ---------------------------------------------------------------------------
# _email_from_membership_login
# ---------------------------------------------------------------------------


def test_email_from_membership_login_valid():
    assert (
        SharePointOnlineBase._email_from_membership_login("i:0#.f|membership|foo@bar.com")
        == "foo@bar.com"
    )


def test_email_from_membership_login_uppercase_normalized():
    assert (
        SharePointOnlineBase._email_from_membership_login("i:0#.f|membership|Foo@BAR.com")
        == "foo@bar.com"
    )


def test_email_from_membership_login_rejects_role_principal():
    # Role principals would otherwise yield "spo-grid-all-users/..." — must reject.
    assert (
        SharePointOnlineBase._email_from_membership_login(
            "c:0-.f|rolemanager|spo-grid-all-users/26adf163-2699-4d04-a0ad-3d935411bf45"
        )
        is None
    )


def test_email_from_membership_login_rejects_federated_group():
    assert (
        SharePointOnlineBase._email_from_membership_login(
            "c:0o.c|federateddirectoryclaimprovider|58cb1814-203a-44d0-8578-b53f63860579"
        )
        is None
    )


def test_email_from_membership_login_rejects_empty():
    assert SharePointOnlineBase._email_from_membership_login("") is None


def test_email_from_membership_login_rejects_malformed():
    assert SharePointOnlineBase._email_from_membership_login("i:0#.f|membership|noat") is None


# ---------------------------------------------------------------------------
# _parse_sp_group_member
# ---------------------------------------------------------------------------


def test_parse_real_user_with_email():
    user = {
        "PrincipalType": 1,
        "LoginName": "i:0#.f|membership|alice@contoso.com",
        "Email": "alice@contoso.com",
        "Title": "Alice",
    }
    assert SharePointOnlineBase._parse_sp_group_member(user) == (
        "alice@contoso.com",
        "user",
    )


def test_parse_real_user_uppercase_email_normalized():
    user = {
        "PrincipalType": 1,
        "LoginName": "i:0#.f|membership|ALICE@CONTOSO.COM",
        "Email": "ALICE@CONTOSO.COM",
        "Title": "Alice",
    }
    assert SharePointOnlineBase._parse_sp_group_member(user) == (
        "alice@contoso.com",
        "user",
    )


def test_parse_real_user_email_empty_fallback_to_login():
    # If Email is missing but LoginName has the membership pattern, use that.
    user = {
        "PrincipalType": 1,
        "LoginName": "i:0#.f|membership|alice@contoso.com",
        "Email": "",
        "Title": "Alice",
    }
    assert SharePointOnlineBase._parse_sp_group_member(user) == (
        "alice@contoso.com",
        "user",
    )


def test_parse_real_user_no_email_no_parseable_login_returns_none():
    # System Account and similar — no Email, no membership LoginName.
    user = {
        "PrincipalType": 1,
        "LoginName": "SHAREPOINT\\system",
        "Email": "",
        "Title": "System Account",
    }
    assert SharePointOnlineBase._parse_sp_group_member(user) is None


def test_parse_role_principal_skipped():
    """Bug B regression test — 'Everyone except external users' must not become a fake user."""
    user = {
        "PrincipalType": 16,
        "LoginName": "c:0-.f|rolemanager|spo-grid-all-users/26adf163-2699-4d04-a0ad-3d935411bf45",
        "Email": "",
        "Title": "Everyone except external users",
    }
    assert SharePointOnlineBase._parse_sp_group_member(user) is None


def test_parse_entra_group_emits_group_membership():
    """Bug C/D regression test — Entra group must be emitted as group-to-group."""
    user = {
        "PrincipalType": 4,
        "LoginName": "c:0o.c|federateddirectoryclaimprovider|58cb1814-203a-44d0-8578-b53f63860579",
        "Email": "neena@neenacorp.onmicrosoft.com",  # group's email, must NOT be used
        "Title": "Neena Members",
    }
    assert SharePointOnlineBase._parse_sp_group_member(user) == (
        "entra:58cb1814-203a-44d0-8578-b53f63860579",
        "group",
    )


def test_parse_entra_group_owner_suffix_stripped():
    """Owner-style claim has `_o` suffix — must strip it to get the bare GUID."""
    login = "c:0o.c|federateddirectoryclaimprovider|58cb1814-203a-44d0-8578-b53f63860579_o"
    user = {
        "PrincipalType": 4,
        "LoginName": login,
        "Email": "neena@neenacorp.onmicrosoft.com",
        "Title": "Neena Owners",
    }
    assert SharePointOnlineBase._parse_sp_group_member(user) == (
        "entra:58cb1814-203a-44d0-8578-b53f63860579",
        "group",
    )


def test_parse_entra_group_uppercase_guid_normalized():
    user = {
        "PrincipalType": 4,
        "LoginName": "c:0o.c|federateddirectoryclaimprovider|58CB1814-203A-44D0-8578-B53F63860579",
        "Title": "Neena Owners",
    }
    assert SharePointOnlineBase._parse_sp_group_member(user) == (
        "entra:58cb1814-203a-44d0-8578-b53f63860579",
        "group",
    )


def test_parse_entra_group_malformed_guid_returns_none():
    user = {
        "PrincipalType": 4,
        "LoginName": "c:0o.c|federateddirectoryclaimprovider|not-a-guid",
        "Title": "Bad Group",
    }
    assert SharePointOnlineBase._parse_sp_group_member(user) is None


def test_parse_security_group_non_federated_returns_none():
    # PrincipalType=4 but not federated — on-prem AD claim, skip.
    user = {
        "PrincipalType": 4,
        "LoginName": "c:0-.f|adclaimprovider|S-1-5-21-...",
        "Title": "On-prem Group",
    }
    assert SharePointOnlineBase._parse_sp_group_member(user) is None


def test_parse_everyone_except_external_claim_returns_synthetic_sentinel():
    """The rolemanager/spo-grid-all-users claim → synthetic group sentinel."""
    user = {
        "PrincipalType": 4,
        "LoginName": (
            "c:0-.f|rolemanager|spo-grid-all-users/26adf163-2699-4d04-a0ad-3d935411bf45"
        ),
        "Title": "Everyone except external users",
    }
    assert SharePointOnlineBase._parse_sp_group_member(user) == (
        EVERYONE_EXCEPT_EXTERNAL_PRINCIPAL,
        "group",
    )


def test_parse_everyone_except_external_uppercase_tenant_id():
    """Tenant ID GUIDs may be upper- or lowercase; both should match."""
    user = {
        "PrincipalType": 4,
        "LoginName": (
            "c:0-.f|rolemanager|spo-grid-all-users/26ADF163-2699-4D04-A0AD-3D935411BF45"
        ),
        "Title": "Everyone except external users",
    }
    assert SharePointOnlineBase._parse_sp_group_member(user) == (
        EVERYONE_EXCEPT_EXTERNAL_PRINCIPAL,
        "group",
    )


def test_parse_other_rolemanager_claim_skipped_and_flagged_as_unrecognized():
    """A different rolemanager claim shouldn't match; should be flagged for logging."""
    user = {
        "PrincipalType": 4,
        "LoginName": "c:0-.f|rolemanager|some-future-claim",
        "Title": "Custom Role",
    }
    assert SharePointOnlineBase._parse_sp_group_member(user) is None
    assert SharePointOnlineBase._is_unrecognized_pt4_login(user) is True


def test_is_unrecognized_pt4_login_false_for_known_shapes():
    """Known PT=4 shapes (Entra group, claim) must NOT be flagged as unrecognized."""
    entra = {
        "PrincipalType": 4,
        "LoginName": (
            "c:0o.c|federateddirectoryclaimprovider|7d344400-39bc-4ee7-aa6e-437bd8de85c0"
        ),
    }
    claim = {
        "PrincipalType": 4,
        "LoginName": "c:0-.f|rolemanager|spo-grid-all-users/26adf163-2699-4d04-a0ad-3d935411bf45",
    }
    assert SharePointOnlineBase._is_unrecognized_pt4_login(entra) is False
    assert SharePointOnlineBase._is_unrecognized_pt4_login(claim) is False


def test_is_unrecognized_pt4_login_false_for_non_pt4():
    """The flag is scoped to PT=4 only; other PrincipalTypes are skipped silently."""
    user = {"PrincipalType": 1, "LoginName": "i:0#.f|membership|alice@example.com"}
    assert SharePointOnlineBase._is_unrecognized_pt4_login(user) is False


def test_parse_distlist_skipped():
    user = {"PrincipalType": 2, "LoginName": "some-dl", "Title": "DL"}
    assert SharePointOnlineBase._parse_sp_group_member(user) is None


def test_parse_spgroup_skipped():
    user = {"PrincipalType": 8, "LoginName": "some-sp", "Title": "SP"}
    assert SharePointOnlineBase._parse_sp_group_member(user) is None


def test_parse_all_catchall_skipped():
    user = {"PrincipalType": 15, "LoginName": "everyone", "Title": "All"}
    assert SharePointOnlineBase._parse_sp_group_member(user) is None


def test_parse_unknown_principal_type_skipped():
    user = {"PrincipalType": 99, "LoginName": "x", "Title": "X"}
    assert SharePointOnlineBase._parse_sp_group_member(user) is None


def test_parse_missing_principal_type_skipped():
    user = {"LoginName": "x", "Title": "X", "Email": "x@y.z"}
    assert SharePointOnlineBase._parse_sp_group_member(user) is None


# ---------------------------------------------------------------------------
# _normalize_site_url
# ---------------------------------------------------------------------------


def test_normalize_site_url_strips_trailing_slash():
    assert (
        SharePointOnlineBase._normalize_site_url("https://contoso.sharepoint.com/sites/X/")
        == "https://contoso.sharepoint.com/sites/X"
    )


def test_normalize_site_url_empty():
    assert SharePointOnlineBase._normalize_site_url("") == ""
    assert SharePointOnlineBase._normalize_site_url(None) == ""  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# _track_entity_groups with site_url scoping
# ---------------------------------------------------------------------------


class _StubEntity:
    def __init__(self, viewers):
        self.access = MagicMock()
        self.access.viewers = viewers


def _bare_base() -> SharePointOnlineBase:
    """Instantiate the base class just enough to exercise tracking logic.

    We bypass the normal source creation path since we only need the tracking
    state and its methods.
    """
    instance = SharePointOnlineBase.__new__(SharePointOnlineBase)
    instance._site_url = ""
    instance._include_personal_sites = False
    instance._include_pages = False
    instance._item_level_entra_groups = set()
    instance._item_level_sp_groups = {}
    return instance


def test_track_entity_groups_scopes_sp_by_site():
    base = _bare_base()
    e = _StubEntity(
        [
            "group:sp:neena_members",
            "group:sp:neena_owners",
            "group:entra:58cb1814-203a-44d0-8578-b53f63860579",
            "user:alice@contoso.com",
        ]
    )
    base._track_entity_groups(e, "https://neenacorp.sharepoint.com/sites/Neena77")

    assert base._item_level_sp_groups == {
        "https://neenacorp.sharepoint.com/sites/Neena77": {
            "sp:neena_members",
            "sp:neena_owners",
        }
    }
    assert base._item_level_entra_groups == {"entra:58cb1814-203a-44d0-8578-b53f63860579"}


def test_track_entity_groups_multiple_sites_keep_separate():
    base = _bare_base()
    base._track_entity_groups(
        _StubEntity(["group:sp:neena_members"]),
        "https://neenacorp.sharepoint.com/sites/A",
    )
    base._track_entity_groups(
        _StubEntity(["group:sp:access_control_tests_owners"]),
        "https://neenacorp.sharepoint.com/sites/B",
    )

    assert base._item_level_sp_groups == {
        "https://neenacorp.sharepoint.com/sites/A": {"sp:neena_members"},
        "https://neenacorp.sharepoint.com/sites/B": {"sp:access_control_tests_owners"},
    }


def test_track_entity_groups_same_name_different_sites_do_not_collide():
    base = _bare_base()
    base._track_entity_groups(
        _StubEntity(["group:sp:members"]),
        "https://neenacorp.sharepoint.com/sites/A",
    )
    base._track_entity_groups(
        _StubEntity(["group:sp:members"]),
        "https://neenacorp.sharepoint.com/sites/B",
    )

    # Same group name but two different sites — must be tracked independently.
    assert set(base._item_level_sp_groups.keys()) == {
        "https://neenacorp.sharepoint.com/sites/A",
        "https://neenacorp.sharepoint.com/sites/B",
    }


def test_track_entity_groups_normalizes_trailing_slash():
    base = _bare_base()
    base._track_entity_groups(
        _StubEntity(["group:sp:x"]),
        "https://neenacorp.sharepoint.com/sites/A/",
    )
    base._track_entity_groups(
        _StubEntity(["group:sp:y"]),
        "https://neenacorp.sharepoint.com/sites/A",
    )
    # Both should land under the same normalized key.
    assert base._item_level_sp_groups == {
        "https://neenacorp.sharepoint.com/sites/A": {"sp:x", "sp:y"}
    }


def test_track_entity_groups_no_access_noop():
    base = _bare_base()
    entity = MagicMock()
    entity.access = None
    base._track_entity_groups(entity, "https://neenacorp.sharepoint.com/sites/A")
    assert base._item_level_sp_groups == {}


def test_track_entity_groups_empty_site_url_still_stores_under_empty_key():
    """Groups are still stored under the empty-string key when no site_url.

    Expansion skips empty-key buckets, so this is effectively a no-op for
    broker purposes but keeps the data structure consistent.
    """
    base = _bare_base()
    base._track_entity_groups(_StubEntity(["group:sp:orphan"]), "")
    assert base._item_level_sp_groups == {"": {"sp:orphan"}}
