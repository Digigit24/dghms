from types import SimpleNamespace

from django.test import SimpleTestCase
from rest_framework.exceptions import PermissionDenied

from apps.clinical.views import (
    _ensure_system_form_mutable,
    _is_system_form_admin,
)


def request(*, permissions=None, is_super_admin=False):
    return SimpleNamespace(
        permissions=permissions or {},
        is_super_admin=is_super_admin,
        tenant_id="tenant-1",
        user_id="user-1",
        roles=[],
    )


SYSTEM_FORM = SimpleNamespace(
    id=1,
    code="system_vitals",
    is_system=True,
)


class SystemFormGuardTests(SimpleTestCase):
    def test_regular_clinical_editor_cannot_mutate_system_form(self):
        actor = request(permissions={"hms.clinical.edit": "all"})

        with self.assertRaises(PermissionDenied):
            _ensure_system_form_mutable(actor, SYSTEM_FORM, "changed")

    def test_full_access_admin_can_mutate_system_form(self):
        actor = request(permissions={"admin.full_access.enabled": True})

        self.assertTrue(_is_system_form_admin(actor))
        _ensure_system_form_mutable(actor, SYSTEM_FORM, "changed")

    def test_super_admin_can_mutate_system_form(self):
        actor = request(is_super_admin=True)

        self.assertTrue(_is_system_form_admin(actor))
        _ensure_system_form_mutable(actor, SYSTEM_FORM, "changed")

    def test_non_system_form_needs_no_override(self):
        actor = request(permissions={"hms.clinical.edit": "all"})
        tenant_form = SimpleNamespace(id=2, code="tenant_form", is_system=False)

        _ensure_system_form_mutable(actor, tenant_form, "changed")
