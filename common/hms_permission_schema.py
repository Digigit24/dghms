SCOPE_OPTIONS = ["own", "team", "all"]


def scope_action():
    return {"type": "scope", "options": SCOPE_OPTIONS}


def boolean_action():
    return {"type": "boolean"}


CRUD_ACTIONS = {
    "view": scope_action(),
    "create": boolean_action(),
    "edit": scope_action(),
    "delete": boolean_action(),
}


CRUD_EXPORT_ACTIONS = {
    **CRUD_ACTIONS,
    "export": scope_action(),
}


HMS_PERMISSION_SCHEMA = {
    "admin": {
        "label": "Administration",
        "resources": {
            "full_access": {
                "label": "Full Admin Access",
                "actions": {
                    "enabled": boolean_action(),
                },
            },
            "users": {
                "label": "Users",
                "actions": CRUD_ACTIONS,
            },
            "roles": {
                "label": "Roles & Permissions",
                "actions": CRUD_ACTIONS,
            },
            "settings": {
                "label": "Tenant Settings",
                "actions": {
                    "view": scope_action(),
                    "edit": scope_action(),
                },
            },
        },
    },
    "hms": {
        "label": "Hospital Management",
        "resources": {
            "hospital": {
                "label": "Hospital Configuration",
                "actions": {
                    "view": scope_action(),
                    "edit_config": scope_action(),
                    "create": boolean_action(),
                    "edit": scope_action(),
                    "delete": boolean_action(),
                },
            },
            "patients": {
                "label": "Patients",
                "actions": CRUD_EXPORT_ACTIONS,
            },
            "doctors": {
                "label": "Doctors & Specialties",
                "actions": {
                    **CRUD_EXPORT_ACTIONS,
                    "set_availability": scope_action(),
                },
            },
            "appointments": {
                "label": "Appointments",
                "actions": {
                    **CRUD_ACTIONS,
                    "cancel": scope_action(),
                    "reschedule": scope_action(),
                },
            },
            "opd": {
                "label": "OPD",
                "actions": {
                    **CRUD_EXPORT_ACTIONS,
                    "consult": scope_action(),
                    "bill": scope_action(),
                    "settings": scope_action(),
                },
            },
            "ipd": {
                "label": "IPD",
                "actions": {
                    **CRUD_EXPORT_ACTIONS,
                    "admit": boolean_action(),
                    "discharge": scope_action(),
                    "transfer": scope_action(),
                    "bill": scope_action(),
                },
            },
            "diagnostics": {
                "label": "Diagnostics",
                "actions": {
                    **CRUD_EXPORT_ACTIONS,
                    "order": boolean_action(),
                    "report": scope_action(),
                    "approve": scope_action(),
                },
            },
            "pharmacy": {
                "label": "Pharmacy",
                "actions": {
                    **CRUD_EXPORT_ACTIONS,
                    "sell": boolean_action(),
                    "stock_adjust": scope_action(),
                    "statistics": scope_action(),
                },
            },
            "payments": {
                "label": "Payments",
                "actions": {
                    **CRUD_EXPORT_ACTIONS,
                    "refund": scope_action(),
                    "reconcile": scope_action(),
                },
            },
            "services": {
                "label": "Services",
                "actions": CRUD_ACTIONS,
            },
            "orders": {
                "label": "Orders & Razorpay",
                "actions": {
                    **CRUD_ACTIONS,
                    "pay": scope_action(),
                    "refund": scope_action(),
                },
            },
            "panchakarma": {
                "label": "Panchakarma",
                "actions": CRUD_ACTIONS,
            },
        },
    },
}
