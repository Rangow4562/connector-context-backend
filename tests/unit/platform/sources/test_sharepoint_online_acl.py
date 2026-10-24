"""Unit tests for SharePoint Online ACL extraction.

Covers ``extract_access_control`` and the rules around how Microsoft Graph
sharing-link permissions map to ``AccessControl``.

Background — two related bug fixes:

1. Organization-scoped sharing links (``link.scope == "organization"``,
   "anyone in your org with the link") used to set ``is_public = True``,
   which made the search broker bypass all viewer checks. Only
   ``link.scope == "anonymous"`` is genuine public access.

2. The previous code attempted to recover sharing-link audience by
   blanket-attaching every site group (including SharingLinks system
   groups for unrelated files) to every file in the site. That over-granted
   massively. The fix is to translate each link permission into the
   specific ``SharingLinks.<itemId>.<scopeRole>.<linkId>`` SP site group
   for that one file, scoped by the file's SharePoint UniqueId.
"""

import pytest

from connector_context.platform.sources.sharepoint_online.acl import (
    extract_access_control,
    link_permission_to_sp_group_viewer,
)

# ---------------------------------------------------------------------------
# Helpers — build minimal Graph permission objects
# ---------------------------------------------------------------------------


def _link_perm(
    scope: str, type_: str = "edit", roles=None, link_id: str = "link-1"
) -> dict:
    """Sharing-link permission with the given scope (no grantedTo principal)."""
    return {
        "id": link_id,
        "roles": roles if roles is not None else ["write"],
        "link": {"scope": scope, "type": type_},
        "grantedToIdentitiesV2": [],
        "grantedToIdentities": [],
    }


def _site_group_perm(name: str, group_id: str = "5", roles=None) -> dict:
    return {
        "id": f"sg-{group_id}",
        "roles": roles if roles is not None else ["write"],
        "grantedToV2": {"siteGroup": {"displayName": name, "id": group_id}},
    }


def _user_perm(email: str, roles=None) -> dict:
    return {
        "id": f"u-{email}",
        "roles": roles if roles is not None else ["read"],
        "grantedToV2": {"user": {"email": email, "displayName": email}},
    }


def _entra_group_perm(group_id: str, roles=None) -> dict:
    return {
        "id": f"eg-{group_id}",
        "roles": roles if roles is not None else ["read"],
        "grantedToV2": {"group": {"id": group_id}},
    }


# ---------------------------------------------------------------------------
# Sharing-link scope handling
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_organization_scoped_link_does_not_set_is_public():
    """Org-scoped link by itself must not flip is_public.

    Regression: the previous behavior treated organization-scoped links as
    fully public, bypassing all viewer checks at search time.
    """
    # Without sp_unique_id the link cannot be translated into a SharingLinks
    # site group viewer either — both halves of the fix combine to give
    # "no public access, no viewer either".
    ac = await extract_access_control([_link_perm("organization")])
    assert ac.is_public is False
    assert ac.viewers == []


@pytest.mark.asyncio
async def test_organization_edit_link_with_sp_unique_id_yields_per_link_viewer():
    """When the file's SP UniqueId is known, an org+edit link translates."""
    perm = _link_perm("organization", type_="edit", link_id="LINK0001")
    ac = await extract_access_control(
        [perm], sp_unique_id="dd7691b0-3468-446f-81b0-72f3bdab7d1f"
    )
    assert ac.is_public is False
    assert ac.viewers == [
        "group:sp:sharinglinks.dd7691b0-3468-446f-81b0-72f3bdab7d1f.organizationedit.link0001"
    ]


@pytest.mark.asyncio
async def test_organization_view_link_translates_to_organizationview_suffix():
    perm = _link_perm("organization", type_="view", link_id="LINK0002")
    ac = await extract_access_control([perm], sp_unique_id="aaaa-bbbb")
    assert ac.viewers == ["group:sp:sharinglinks.aaaa-bbbb.organizationview.link0002"]


@pytest.mark.asyncio
async def test_users_scope_link_translates_to_flexible_suffix():
    """Empirically verified: both users+edit and users+view collapse to Flexible."""
    perm_edit = _link_perm("users", type_="edit", link_id="LINKE")
    perm_view = _link_perm("users", type_="view", link_id="LINKV")
    ac_e = await extract_access_control([perm_edit], sp_unique_id="ITEM1")
    ac_v = await extract_access_control([perm_view], sp_unique_id="ITEM1")
    assert ac_e.viewers == ["group:sp:sharinglinks.item1.flexible.linke"]
    assert ac_v.viewers == ["group:sp:sharinglinks.item1.flexible.linkv"]


@pytest.mark.asyncio
async def test_anonymous_link_does_not_get_translated_to_viewer():
    """Anonymous → is_public, never a SharingLinks viewer."""
    perm = _link_perm("anonymous", type_="view", link_id="LINKA")
    ac = await extract_access_control([perm], sp_unique_id="ITEM1")
    assert ac.is_public is True
    assert ac.viewers == []


@pytest.mark.asyncio
async def test_anonymous_link_sets_is_public():
    ac = await extract_access_control([_link_perm("anonymous")])
    assert ac.is_public is True


@pytest.mark.asyncio
async def test_org_and_anonymous_links_together_still_public_via_anonymous():
    ac = await extract_access_control([_link_perm("organization"), _link_perm("anonymous")])
    assert ac.is_public is True


@pytest.mark.asyncio
async def test_users_scoped_link_does_not_set_is_public():
    """``users``-scoped links target named recipients, not the org."""
    ac = await extract_access_control([_link_perm("users")])
    assert ac.is_public is False


@pytest.mark.asyncio
async def test_unknown_link_scope_does_not_set_is_public():
    """Future / unrecognized scopes default to non-public."""
    ac = await extract_access_control([_link_perm("someFutureScope")])
    assert ac.is_public is False


# ---------------------------------------------------------------------------
# Mixed permissions — the realistic case
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_org_link_alongside_explicit_grants_extracts_grants_and_link_group():
    """Org-link plus explicit grants → both end up in viewers.

    Mirrors the Mistral bug-report payload shape: a file with one
    organization-scoped sharing link plus inherited site-group grants.
    Post-fix, is_public is False, all explicit grants are present, and
    the per-link SharingLinks site group is included exactly once.
    """
    perms = [
        _link_perm("organization", link_id="LINK0001"),
        _site_group_perm("Access Control Tests Owners", group_id="3", roles=["owner"]),
        _site_group_perm("Access Control Tests Members", group_id="5", roles=["write"]),
        _site_group_perm("Access Control Tests Visitors", group_id="4", roles=["read"]),
    ]
    ac = await extract_access_control(perms, sp_unique_id="ITEM1")
    assert ac.is_public is False
    assert set(ac.viewers) == {
        "group:sp:access_control_tests_owners",
        "group:sp:access_control_tests_members",
        "group:sp:access_control_tests_visitors",
        "group:sp:sharinglinks.item1.organizationedit.link0001",
    }


@pytest.mark.asyncio
async def test_user_and_entra_group_grants_extracted():
    perms = [
        _user_perm("alice@example.com"),
        _entra_group_perm("11111111-2222-3333-4444-555555555555"),
    ]
    ac = await extract_access_control(perms)
    assert ac.is_public is False
    assert set(ac.viewers) == {
        "user:alice@example.com",
        "group:entra:11111111-2222-3333-4444-555555555555",
    }


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_empty_permissions_returns_empty_access_control():
    ac = await extract_access_control([])
    assert ac.is_public is False
    assert ac.viewers == []


@pytest.mark.asyncio
async def test_permission_without_read_role_is_ignored():
    """Roles other than read/write/owner/sp.full control don't grant viewing."""
    perms = [
        {
            "id": "restricted",
            "roles": ["restricted"],
            "grantedToV2": {"user": {"email": "alice@example.com"}},
        },
    ]
    ac = await extract_access_control(perms)
    assert ac.is_public is False
    assert ac.viewers == []


@pytest.mark.asyncio
async def test_org_link_without_read_role_is_ignored_entirely():
    """A link without a read-equivalent role doesn't even reach scope check."""
    perms = [
        {
            "id": "link-restricted",
            "roles": ["restricted"],
            "link": {"scope": "organization"},
        }
    ]
    ac = await extract_access_control(perms)
    assert ac.is_public is False
    assert ac.viewers == []


@pytest.mark.asyncio
async def test_duplicate_principal_only_added_once():
    perms = [
        _user_perm("alice@example.com", roles=["read"]),
        _user_perm("alice@example.com", roles=["write"]),
    ]
    ac = await extract_access_control(perms)
    assert ac.viewers == ["user:alice@example.com"]


# ---------------------------------------------------------------------------
# link_permission_to_sp_group_viewer — None-return paths
# ---------------------------------------------------------------------------


def test_link_translation_returns_none_without_sp_unique_id():
    """No SP UniqueId means we can't construct the group name — return None."""
    perm = _link_perm("organization", link_id="L1")
    assert link_permission_to_sp_group_viewer(perm, None) is None


def test_link_translation_returns_none_for_non_link_perm():
    """A non-link permission is not a sharing link — return None."""
    perm = {"id": "x", "roles": ["read"], "grantedToV2": {"user": {"email": "a@b.com"}}}
    assert link_permission_to_sp_group_viewer(perm, "ITEM1") is None


def test_link_translation_returns_none_for_anonymous():
    perm = _link_perm("anonymous", link_id="L1")
    assert link_permission_to_sp_group_viewer(perm, "ITEM1") is None


def test_link_translation_returns_none_for_unknown_scope():
    """Unknown / future scope: be conservative, don't fabricate a viewer."""
    perm = {
        "id": "L1",
        "roles": ["read"],
        "link": {"scope": "future-scope", "type": "edit"},
    }
    assert link_permission_to_sp_group_viewer(perm, "ITEM1") is None


def test_link_translation_returns_none_when_link_id_missing():
    perm = {"id": "", "roles": ["read"], "link": {"scope": "organization", "type": "edit"}}
    assert link_permission_to_sp_group_viewer(perm, "ITEM1") is None
